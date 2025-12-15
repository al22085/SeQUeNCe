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
import csv
import json
import sys
import numpy as np
from pathlib import Path
from typing import Sequence

# Ensure repository root is importable when run as a script
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

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
        help="試行回数: fixed_successes は目標成功数、fixed_attempts は試行回数、fixed_time はメモリ数の目安。",
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
        default=None,
        help="DQT 用: トランスデューサ経路の成功確率（後方互換用。dqt-eta-* を優先）",
    )
    parser.add_argument(
        "--dqt-eta-source",
        type=float,
        default=1.0,
        help="DQT 用: 送信側トランスデューサ効率（デフォルト 1.0, dest=0.7 で 0.7 に一致）",
    )
    parser.add_argument(
        "--dqt-eta-dest",
        type=float,
        default=0.7,
        help="DQT 用: 受信側トランスデューサ効率（デフォルト 0.7, source=1.0 で 0.7 に一致）",
    )
    parser.add_argument(
        "--distance",
        type=float,
        default=1e4,
        help="3ノード線形トポロジーで使うチャネル距離（メートル）。",
    )
    parser.add_argument(
        "--distances",
        type=str,
        default=None,
        help="カンマ区切りの距離リスト（指定時は distance を無視してスイープ）。",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="結果を書き出すファイルパス（拡張子 .csv または .json を推奨）。",
    )
    parser.add_argument(
        "--format",
        choices=["md", "csv", "json"],
        default="md",
        help="標準出力に出す形式。md=Markdown テーブル。",
    )
    parser.add_argument(
        "--mode",
        choices=["fixed_successes", "fixed_attempts", "fixed_time"],
        default="fixed_successes",
        help="attempt 定義を明示: fixed_successes=成功 N 回達成まで, fixed_attempts=試行 N 回まで, fixed_time=stop_time まで走らせる。",
    )
    parser.add_argument(
        "--stop-time",
        type=float,
        default=5e12,
        help="fixed_time モード時のタイムライン stop_time（ピコ秒）。他のモードでは安全上限として使用。",
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


def build_line_network(
    tl: Timeline, num_memories: int, base_seed: int | None, distance: float
) -> tuple[QuantumRouter, QuantumRouter, BSMNode]:
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


def run_experiment(
    strategy: str,
    num_trials: int,
    seed: int | None,
    eta_source: float,
    eta_dest: float,
    qt_eff: float | None,
    dqt_eta_source: float,
    dqt_eta_dest: float,
    distance: float,
    mode: str,
    stop_time: float,
) -> dict[str, float | int | str | float]:
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
        # DQT のトランスデューサ成功確率 = eta_source * eta_dest (qt_eff 指定時はそれを優先)
        success_prob = qt_eff if qt_eff is not None else dqt_eta_source * dqt_eta_dest

        def dqt_create(cls, owner, name, middle, other, memory, **kwargs):
            kwargs.setdefault("qt_emitter", _make_dqt_emitter(owner, memory, middle, success_prob))
            return orig_create(cls, owner, name, middle, other, memory, **kwargs)

        EntanglementGenerationA.create = classmethod(dqt_create)  # type: ignore[assignment]
        patched = True

    successes = 0
    failures = 0
    batch_size = 50  # 一度に走らせるメモリ数（大きすぎるとタイムラインが重いので分割）
    target_successes = num_trials if mode == "fixed_successes" else None
    target_attempts = num_trials if mode == "fixed_attempts" else None

    while True:
        remaining = batch_size
        if target_successes is not None:
            remaining = min(batch_size, max(target_successes - successes, 1))
        if target_attempts is not None:
            remaining = min(batch_size, max(target_attempts - (successes + failures), 1))

        tl = Timeline(stop_time=int(stop_time))  # 長すぎるイベント列を避けるためタイムアウトを設定
        batch_seed = None if seed is None else seed + successes + failures
        e0, e1, _ = build_line_network(tl, remaining, base_seed=batch_seed, distance=distance)

        path = [e0.name, e1.name]
        install_eg_rules([e0, e1], path, remaining)

        stats = {"succ": 0, "fail": 0}
        original_update = e0.resource_manager.update

        def counting_update(protocol, memory, state):
            if state == "ENTANGLED":
                stats["succ"] += 1
            elif state == "RAW" and protocol is not None:
                stats["fail"] += 1
            attempts_now = stats["succ"] + stats["fail"] + successes + failures

            # attempt 定義: RM.update が成功/失敗で呼ばれるたびに 1 カウント（BK/DQT/EQT 共通）
            if mode == "fixed_attempts" and target_attempts is not None and attempts_now >= target_attempts:
                tl.stop()
            if mode == "fixed_successes" and target_successes is not None and (stats["succ"] + successes) >= target_successes:
                tl.stop()
            return original_update(protocol, memory, state)

        e0.resource_manager.update = counting_update  # type: ignore[method-assign]

        tl.init()
        tl.run()

        successes += stats["succ"]
        failures += stats["fail"]

        attempts = successes + failures
        if mode == "fixed_attempts" and target_attempts is not None and attempts >= target_attempts:
            break
        if mode == "fixed_successes" and target_successes is not None and successes >= target_successes:
            break
        if mode == "fixed_time":
            break

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
        "distance": distance,
        "eta_source": eta_source if protocol_type == EQT else None,
        "eta_dest": eta_dest if protocol_type == EQT else None,
        "mode": mode,
        "stop_time": stop_time,
    }


def _parse_distance_list(args: argparse.Namespace) -> list[float]:
    if args.distances:
        return [float(x) for x in args.distances.split(",") if x.strip()]
    return [float(args.distance)]


def _maybe_warn_unused_eta(strategy: str, eta_source: float, eta_dest: float) -> None:
    if strategy != "EQT" and (eta_source != 0.8 or eta_dest != 0.8):
        print("[info] eta-source/dest are ignored for non-EQT strategies.")


def _emit_markdown(results: list[dict]) -> None:
    headers = ["strategy", "mode", "distance", "eta_source", "eta_dest", "trials", "successes", "attempts", "availability"]
    print("| " + " | ".join(headers) + " |")
    print("|" + " --- |" * len(headers))
    for r in results:
        row = [
            r["strategy"],
            r["mode"],
            f"{r['distance']:.0f}",
            f"{r.get('eta_source', 0.8):.2f}" if r.get("eta_source") is not None else "-",
            f"{r.get('eta_dest', 0.8):.2f}" if r.get("eta_dest") is not None else "-",
            str(r["num_trials"]),
            str(r["num_entangled"]),
            str(r["num_attempts"]),
            f"{r['availability']:.3f}",
        ]
        print("| " + " | ".join(row) + " |")


def _write_out(path: Path, results: list[dict]) -> None:
    if path.suffix.lower() == ".json":
        path.write_text(json.dumps(results, indent=2))
    else:
        # default to csv
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["strategy", "mode", "distance", "eta_source", "eta_dest", "num_trials", "num_entangled", "num_attempts", "availability"],
            )
            writer.writeheader()
            for r in results:
                writer.writerow(r)


def main():
    args = parse_args()
    _maybe_warn_unused_eta(args.strategy, args.eta_source, args.eta_dest)
    distances = _parse_distance_list(args)

    results = []
    for dist in distances:
        result = run_experiment(
            strategy=args.strategy,
            num_trials=args.num_trials,
            seed=args.seed,
            eta_source=args.eta_source,
            eta_dest=args.eta_dest,
            qt_eff=args.qt_eff,
            distance=dist,
            mode=args.mode,
            stop_time=args.stop_time,
            dqt_eta_source=args.dqt_eta_source,
            dqt_eta_dest=args.dqt_eta_dest,
        )
        results.append(result)

    if args.format == "md":
        _emit_markdown(results)
    elif args.format == "json":
        print(json.dumps(results, indent=2))
    elif args.format == "csv":
        writer = csv.DictWriter(
            sys.stdout,
            fieldnames=["strategy", "mode", "distance", "eta_source", "eta_dest", "num_trials", "num_entangled", "num_attempts", "availability"],
        )
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    if args.out is not None:
        _write_out(args.out, results)


if __name__ == "__main__":
    main()
