"""
BK / DQT / EQT を同じネットワーク構成で NUM_TESTS 回走らせて、
成功数と成功率の比較表を Markdown で出力するスクリプト。

使い方:
  python scripts/qt_dq_bk_table.py
"""

from __future__ import annotations

import math

from sequence.constants import BARRET_KOK, DQT, EQT
from sequence.components.bsm import make_bsm
from sequence.components.memory import MemoryArray
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.kernel.timeline import Timeline
from sequence.kernel.event import Event
from sequence.kernel.process import Process
from sequence.entanglement_management.generation import (
    EntanglementGenerationA,
    EntanglementGenerationB,
)
from sequence.topology.node import Node


# ======== 以下、tests/entanglement_management/test_generation.py からの軽いコピー ========


class ResourceManager:
    def __init__(self):
        self.log: list[tuple[object, str]] = []

    def update(self, protocol, memory, state):
        # memory: Memory, state: "RAW" or "ENTANGLED"
        self.log.append((memory, state))


class FakeRouter(Node):
    def __init__(self, name, tl, **kwargs):
        super().__init__(name, tl)
        self.resource_manager = ResourceManager()
        self.memory_array: MemoryArray | None = None

    def init(self):
        # MemoryArray の receiver を自分に向ける
        self.memory_array.add_receiver(self)

    def get(self, photon, **kwargs):
        # BSM ノードから帰ってきた photon を適切な宛先に送る
        dst = kwargs["dst"]
        self.send_qubit(dst, photon)


class FakeBSMNode(Node):
    def __init__(self, name, tl, **kwargs):
        super().__init__(name, tl)
        self.msg_log = []

    def receive_message(self, src: str, msg: "Message"):
        self.msg_log.append((self.timeline.now(), src, msg))
        super().receive_message(src, msg)

    def receive_qubit(self, src: str, qubit):
        # QuantumChannel から photon を受け取ったら BSM に流す
        self.bsm.get(qubit)


# ======== BK/DQT/EQT を走らせる共通実験関数 ========


def run_generation_experiment(
    label: str,
    protocol_type: str,
    num_tests: int = 200,
    fidelity: float | None = None,
    seed_base: int = 0,
    *,
    eta_source: float | None = None,
    eta_dest: float | None = None,
) -> dict:
    """単一戦略（BK / DQT / EQT）を num_tests 回試し、成功統計を返す。

    - protocol_type に応じて EntanglementGenerationA/B の global_type を切り替える
    - EQT の場合だけ eta_source / eta_dest を A 側プロトコルに渡す
    """

    # DQT / EQT クラスを registry に登録させるための import（重複 import OK）
    import sequence.entanglement_management.generation.qt_dq  # noqa: F401
    import sequence.entanglement_management.generation.qt_eqt  # noqa: F401

    # グローバルタイプを退避して指定のタイプに変更
    old_a = EntanglementGenerationA.get_global_type()
    old_b = EntanglementGenerationB.get_global_type()
    EntanglementGenerationA.set_global_type(protocol_type)
    EntanglementGenerationB.set_global_type(protocol_type)

    try:
        tl = Timeline()

        e0 = FakeRouter("e0", tl)
        m0 = FakeBSMNode("m0", tl)
        e1 = FakeRouter("e1", tl)
        e0.set_seed(seed_base + 0)
        m0.set_seed(seed_base + 1)
        e1.set_seed(seed_base + 2)

        # --- Quantum / Classical チャネルは test_generation_run と同じ ---
        qc0 = QuantumChannel("qc_e0m0", tl, 0, 1e3)
        qc1 = QuantumChannel("qc_e1m0", tl, 0, 1e3)
        qc0.set_ends(e0, m0.name)
        qc1.set_ends(e1, m0.name)

        for src in [e0, e1, m0]:
            for dst in [e0, e1, m0]:
                if src.name != dst.name:
                    cc = ClassicalChannel(
                        "cc_%s_%s" % (src.name, dst.name),
                        tl,
                        1e3,
                        delay=1e9,
                    )
                    cc.set_ends(src, dst.name)

        # --- MemoryArray & BSM も test_generation_run と同じ ---
        if fidelity is None:
            e0.memory_array = MemoryArray(
                "e0.memory_array", tl, num_memories=num_tests
            )
            e1.memory_array = MemoryArray(
                "e1.memory_array", tl, num_memories=num_tests
            )
        else:
            e0.memory_array = MemoryArray(
                "e0.memory_array",
                tl,
                fidelity=fidelity,
                num_memories=num_tests,
            )
            e1.memory_array = MemoryArray(
                "e1.memory_array",
                tl,
                fidelity=fidelity,
                num_memories=num_tests,
            )

        e0.memory_array.owner = e0
        e1.memory_array.owner = e1

        detectors = [{"efficiency": 1, "count_rate": 1e11}] * 2
        m0.bsm = make_bsm(
            "m0.bsm",
            tl,
            encoding_type="single_atom",
            detectors=detectors,
        )
        m0.bsm.owner = m0

        # middle protocol (B 側)
        eg_m0 = EntanglementGenerationB.create(m0, "eg_m0", others=["e0", "e1"])
        m0.bsm.attach(eg_m0)

        tl.init()

        protocols_e0 = []
        protocols_e1 = []

        # A 側プロトコルを e0/e1 に貼って start をスケジュール
        for i in range(num_tests):
            name0, name1 = [f"eg_{protocol_type}_e{j}[{i}]" for j in range(2)]

            # EQT の場合だけトランスデューサ効率を渡す（None のときは 1.0 にフォールバック）
            if protocol_type == EQT:
                proto_kwargs = {
                    "eta_source": 1.0 if eta_source is None else eta_source,
                    "eta_dest": 1.0 if eta_dest is None else eta_dest,
                }
            else:
                proto_kwargs = {}

            protocol0 = EntanglementGenerationA.create(
                e0,
                name0,
                middle="m0",
                other="e1",
                memory=e0.memory_array[i],
                **proto_kwargs,
            )
            e0.protocols.append(protocol0)
            protocols_e0.append(protocol0)

            protocol1 = EntanglementGenerationA.create(
                e1,
                name1,
                middle="m0",
                other="e0",
                memory=e1.memory_array[i],
                **proto_kwargs,
            )
            e1.protocols.append(protocol1)
            protocols_e1.append(protocol1)

            protocol0.set_others(
                protocol1.name, e1.name, [e1.memory_array[i].name]
            )
            protocol1.set_others(
                protocol0.name, e0.name, [e0.memory_array[i].name]
            )

            for protocol in (protocols_e0[i], protocols_e1[i]):
                process = Process(protocol, "start", [])
                event = Event(i * 1e12, process)
                tl.schedule(event)

        tl.run()

        # ResourceManager.log は test_generation_run と同じ形式:
        # [(memory, state), ...]  state は "RAW" or "ENTANGLED"
        assert len(e0.resource_manager.log) == num_tests

        success = 0
        for mem, state in e0.resource_manager.log:
            if state != "RAW":
                success += 1

        fail = num_tests - success
        success_rate = success / num_tests if num_tests > 0 else math.nan

        return {
            "label": label,
            "protocol_type": protocol_type,
            "num_tests": num_tests,
            "success": success,
            "fail": fail,
            "success_rate": success_rate,
            "eta_source": eta_source,
            "eta_dest": eta_dest,
        }

    finally:
        # グローバルタイプを元に戻す
        EntanglementGenerationA.set_global_type(old_a)
        EntanglementGenerationB.set_global_type(old_b)


# ======== 表の整形 & main ========


def format_markdown_table(rows: list[dict]) -> str:
    headers = [
        "label",
        "protocol_type",
        "eta_source",
        "eta_dest",
        "num_tests",
        "success",
        "fail",
        "success_rate",
    ]

    lines = []
    # header
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")

    for row in rows:
        line = "| " + " | ".join(
            [
                str(row.get("label", "")),
                str(row["protocol_type"]),
                str(row["eta_source"]) if row.get("eta_source") is not None else "-",
                str(row["eta_dest"]) if row.get("eta_dest") is not None else "-",
                str(row["num_tests"]),
                str(row["success"]),
                str(row["fail"]),
                f"{row['success_rate']:.3f}",
            ]
        ) + " |"
        lines.append(line)

    return "\n".join(lines)


def main():
    NUM_TESTS = 200  # 必要に応じて増やす（論文の統計に合わせるなら 1e4 とかでもOK）

    rows: list[dict] = []

    # BK（ベースライン）
    rows.append(
        run_generation_experiment(
            label="BK",
            protocol_type=BARRET_KOK,
            num_tests=NUM_TESTS,
            seed_base=0,
        )
    )

    # DQT（Direct Quantum Transduction）
    rows.append(
        run_generation_experiment(
            label="DQT",
            protocol_type=DQT,
            num_tests=NUM_TESTS,
            seed_base=1000,
        )
    )

    # EQT（Entanglement-assisted Quantum Transduction）
    rows.append(
        run_generation_experiment(
            label="EQT",
            protocol_type=EQT,
            num_tests=NUM_TESTS,
            seed_base=2000,
            eta_source=0.8,  # 有効変換効率を明示（例: 送信/受信とも 0.8）
            eta_dest=0.8,
        )
    )

    # Markdown テーブルとして結果を出力（eta_* は EQT のみ意味を持つ）
    print(format_markdown_table(rows))


if __name__ == "__main__":
    main()
