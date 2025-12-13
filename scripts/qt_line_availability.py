"""
BK / DQT / EQT を通常の ResourceManager / RuleManager / Network 経路で動かし、
3 ノード直線トポロジー（e0 - m0 - e1）での簡易可用性を測るスクリプト。

使い方:
  python scripts/qt_line_availability.py --strategy BK
  python scripts/qt_line_availability.py --strategy DQT
  python scripts/qt_line_availability.py --strategy EQT
"""

from __future__ import annotations

import argparse
import numpy as np
from typing import Sequence

# 各戦略の定数をまとめて読み込む（EQT/DQT の registry 登録用 import もここで実行）
from sequence.constants import BARRET_KOK, DQT, EQT
from sequence.entanglement_management.generation import (
    EntanglementGenerationA,
    EntanglementGenerationB,
)
import sequence.entanglement_management.generation.qt_dq  # noqa: F401
import sequence.entanglement_management.generation.qt_eqt  # noqa: F401
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.kernel.timeline import Timeline
from sequence.resource_management.rule_manager import Rule
from sequence.network_management.reservation import eg_rule_action1, eg_rule_action2, eg_rule_condition
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.utils.availability import availability_from_counts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BK/DQT/EQT の可用性簡易比較")
    parser.add_argument(
        "--strategy",
        choices=["BK", "DQT", "EQT"],
        default="BK",
        help="使用する EG 戦略 (BK / DQT / EQT)",
    )
    parser.add_argument(
        "--num-trials",
        type=int,
        default=20,
        help="試行回数 (= 予約するメモリペア数)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="乱数シード（同じシードなら結果が再現する）",
    )
    parser.add_argument(
        "--eta-source",
        type=float,
        default=0.8,
        help="EQT 用: 送信側トランスデューサ効率（デフォルト 0.8）",
    )
    parser.add_argument(
        "--eta-dest",
        type=float,
        default=0.8,
        help="EQT 用: 受信側トランスデューサ効率（デフォルト 0.8）",
    )
    parser.add_argument(
        "--qt-eff",
        type=float,
        default=0.7,
        help="DQT 用: トランスデューサ経路の成功確率（デフォルト 0.7）",
    )
    return parser.parse_args()


def set_strategy(strategy: str) -> str:
    """文字列で受け取った戦略を EntanglementGeneration の global_type に反映する。"""
    if strategy == "BK":
        protocol_type = BARRET_KOK
    elif strategy == "DQT":
        protocol_type = DQT
    elif strategy == "EQT":
        protocol_type = EQT
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    # A/B 双方のグローバル設定を揃える（EQT/DQT でも B 側がズレないようにする）
    EntanglementGenerationA.set_global_type(protocol_type)
    EntanglementGenerationB.set_global_type(protocol_type)
    return protocol_type


def build_line_network(tl: Timeline, num_memories: int, base_seed: int | None) -> tuple[QuantumRouter, QuantumRouter, BSMNode]:
    """3 ノード直線（e0-m0-e1）のネットワークを構築し、チャネルを張る。

    - 量子チャネルには現実的な減衰を設定してロスを入れる（可用性が 1.0 にならないようにする）
    - BSM 検出効率も <1 にして成功確率を下げる
    """
    e0 = QuantumRouter("e0", tl, memo_size=num_memories, seed=None if base_seed is None else base_seed + 0)
    e1 = QuantumRouter("e1", tl, memo_size=num_memories, seed=None if base_seed is None else base_seed + 1)
    detectors = [{"efficiency": 0.8, "count_rate": 1e11}] * 2  # BSM 検出器の効率を落としておく
    m0 = BSMNode("m0", tl, [e0.name, e1.name], seed=None if base_seed is None else base_seed + 2,
                 component_templates={"SingleAtomBSM": {"detectors": detectors}})

    # 量子チャネル（左右から BSM へ）。遅延は適当な値を設定。
    # 減衰は 0.2 dB/km 相当（2e-4 dB/m）、距離 10 km とする
    attenuation = 2e-4
    distance = 1e4
    qc_e0_m0 = QuantumChannel("qc_e0_m0", tl, attenuation, distance)
    qc_e1_m0 = QuantumChannel("qc_e1_m0", tl, attenuation, distance)
    qc_e0_m0.set_ends(e0, m0.name)
    qc_e1_m0.set_ends(e1, m0.name)

    # BSM ノード対応表（entanglement generation がどの BSM を見るか）
    e0.add_bsm_node(m0.name, e1.name)
    e1.add_bsm_node(m0.name, e0.name)

    # 古典チャネルは e0/e1/m0 間を全結線しておく（EG の交信と RM 間のリクエスト用）
    for src in (e0, e1, m0):
        for dst in (e0, e1, m0):
            if src.name == dst.name:
                continue
            cc = ClassicalChannel(f"cc_{src.name}_{dst.name}", tl, 1e3, delay=1e9)
            cc.set_ends(src, dst.name)

    return e0, e1, m0


def install_eg_rules(routers: Sequence[QuantumRouter], path: list[str], num_memories: int) -> None:
    """最小限の EG ルールだけを各ルータにインストールする（EP/ES は無効化）。"""
    for router in routers:
        rm = router.resource_manager
        index = path.index(router.name)
        memory_indices = list(range(num_memories))

        if index > 0:
            # responder 側（path[1]）: action1 は REQUEST を送らず待ち受け
            condition_args = {"memory_indices": memory_indices}
            action_args = {"mid": router.map_to_middle_node[path[index - 1]], "path": path, "index": index}
            rule = Rule(10, eg_rule_action1, eg_rule_condition, action_args, condition_args)
        else:
            # initiator 側（path[0]）: action2 がリクエストを送ってペアリングする
            condition_args = {"memory_indices": memory_indices}
            action_args = {"mid": router.map_to_middle_node[path[index + 1]],
                           "path": path, "index": index, "name": router.name, "reservation": None}
            rule = Rule(10, eg_rule_action2, eg_rule_condition, action_args, condition_args)

        rm.load(rule)


def _make_dqt_emitter(owner, memory, middle: str, success_prob: float):
    """DQT 用の簡易トランスデューサ エミッタ（成功確率 success_prob）。"""

    class DQEmitter:
        def start(self):
            node = owner
            if node is None:
                # Memory -> MemoryArray -> owner から辿って Node を取得（owner が未設定な場合のフォールバック）
                node = getattr(getattr(memory, "memory_array", None), "owner", None)
            rng = node.get_generator() if node is not None else np.random.default_rng()
            if rng.random() < success_prob:
                memory.excite(middle)
            # 失敗時は何もしない → BK の excite をスキップし、成功率が下がる

    return DQEmitter()


def run_experiment(strategy: str, num_trials: int, seed: int | None, eta_source: float, eta_dest: float, qt_eff: float) -> dict[str, float | int | str]:
    """指定戦略でシミュレーションを走らせ、簡易可用性を返す。"""
    protocol_type = set_strategy(strategy)

    # 乱数シードを固定することで BK/DQT/EQT の結果を再現できるようにする
    if seed is not None:
        np.random.seed(seed)

    # EQT の場合は eta をデフォルト値 (<1) に差し込む
    orig_create = EntanglementGenerationA.create.__func__
    patched = False
    if protocol_type == EQT:

        def eqt_create(cls, owner, name, middle, other, memory, **kwargs):
            kwargs.setdefault("eta_source", eta_source)
            kwargs.setdefault("eta_dest", eta_dest)
            return orig_create(cls, owner, name, middle, other, memory, **kwargs)

        EntanglementGenerationA.create = classmethod(eqt_create)  # type: ignore[assignment]
        patched = True
    elif protocol_type == DQT:

        def dqt_create(cls, owner, name, middle, other, memory, **kwargs):
            kwargs.setdefault("qt_emitter", _make_dqt_emitter(owner, memory, middle, qt_eff))
            return orig_create(cls, owner, name, middle, other, memory, **kwargs)

        EntanglementGenerationA.create = classmethod(dqt_create)  # type: ignore[assignment]
        patched = True

    successes = 0
    failures = 0
    processed = 0
    batch_size = 50  # 一度に走らせるメモリ数（大きすぎるとタイムラインが重いので分割）

    while processed < num_trials:
        batch_mem = min(batch_size, num_trials - processed)
        tl = Timeline(stop_time=int(5e12))  # 長すぎるイベント列を避けるためタイムアウトを設定
        batch_seed = None if seed is None else seed + processed
        e0, e1, _ = build_line_network(tl, batch_mem, base_seed=batch_seed)

        path = [e0.name, e1.name]
        install_eg_rules([e0, e1], path, batch_mem)

        stats = {"succ": 0, "fail": 0}
        original_update = e0.resource_manager.update

        def counting_update(protocol, memory, state):
            if state == "ENTANGLED":
                stats["succ"] += 1
            elif state == "RAW" and protocol is not None:
                stats["fail"] += 1
            return original_update(protocol, memory, state)

        e0.resource_manager.update = counting_update  # type: ignore[method-assign]

        tl.init()
        tl.run()

        successes += stats["succ"]
        failures += stats["fail"]
        processed += batch_mem

    # パッチした create を元に戻す（他コードへの副作用を避ける）
    if patched:
        EntanglementGenerationA.create = classmethod(orig_create)  # type: ignore[assignment]

    attempts = successes + failures
    availability = availability_from_counts(successes, attempts)

    return {
        "strategy": strategy,
        "protocol_type": protocol_type,
        "num_trials": num_trials,
        "num_entangled": successes,
        "num_attempts": attempts,
        "availability": availability,
    }


def main():
    args = parse_args()
    result = run_experiment(
        strategy=args.strategy,
        num_trials=args.num_trials,
        seed=args.seed,
        eta_source=args.eta_source,
        eta_dest=args.eta_dest,
        qt_eff=args.qt_eff,
    )

    # シンプルな可用性サマリを出力（EQT の eta_* は現状デフォルト 1.0）
    print("strategy:", result["strategy"])
    print("protocol_type:", result["protocol_type"])
    print("num_trials:", result["num_trials"])
    print("num_entangled:", result["num_entangled"])
    print("num_attempts:", result["num_attempts"])
    print(f"availability: {result['availability']:.3f}")


if __name__ == "__main__":
    main()
