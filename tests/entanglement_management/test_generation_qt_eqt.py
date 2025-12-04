import pytest
import sequence.entanglement_management.generation.qt_eqt  # noqa: F401  # registry 登録のため import だけする

from sequence.constants import EQT
from sequence.entanglement_management.generation import (
    EntanglementGenerationA,
    EntanglementGenerationB,
)


def test_eqt_registered_in_registry():
    """EQT プロトコルが registry に登録されていることを確認するテスト。"""
    assert EQT in EntanglementGenerationA.list_protocols()
    assert EQT in EntanglementGenerationB.list_protocols()


def test_eqt_factory_returns_eq_transduction_a():
    """set_global_type(EQT) で A 側 factory が EqTransductionA を返すことを確認。"""
    from sequence.entanglement_management.generation.qt_eqt import EqTransductionA
    from sequence.kernel.timeline import Timeline
    from sequence.topology.node import Node
    from sequence.components.memory import MemoryArray

    tl = Timeline()
    node = Node("n1", tl)
    mem_array = MemoryArray("mem", tl)
    mem_array.owner = node

    old_type = EntanglementGenerationA.get_global_type()
    try:
        EntanglementGenerationA.set_global_type(EQT)
        proto = EntanglementGenerationA.create(
            owner=node,
            name="eg_eqt",
            middle="m",
            other="n2",
            memory=mem_array[0],
        )
        assert isinstance(proto, EqTransductionA)
        assert proto.protocol_type == EQT
    finally:
        EntanglementGenerationA.set_global_type(old_type)


def test_eqt_factory_returns_eq_transduction_b():
    """set_global_type(EQT) で B 側 factory が EqTransductionB を返すことを確認。"""
    from sequence.entanglement_management.generation.qt_eqt import EqTransductionB
    from sequence.kernel.timeline import Timeline
    from sequence.topology.node import Node

    tl = Timeline()

    class DummyBSMNode(Node):
        """BSMNode 代わりの最小限ダミー（名称だけ使う）。"""

    node = DummyBSMNode("bsm", tl)

    old_type = EntanglementGenerationB.get_global_type()
    try:
        EntanglementGenerationB.set_global_type(EQT)
        proto = EntanglementGenerationB.create(
            owner=node,
            name="eg_eqt_b",
            others=["e0", "e1"],
        )
        assert isinstance(proto, EqTransductionB)
        assert proto.protocol_type == EQT
    finally:
        EntanglementGenerationB.set_global_type(old_type)


def test_eqt_effective_eta_clamped():
    """eta_source と eta_dest の積が 0〜1 にクリップされることを確認するテスト。"""
    from sequence.kernel.timeline import Timeline
    from sequence.topology.node import Node
    from sequence.components.memory import MemoryArray
    from sequence.entanglement_management.generation.qt_eqt import EqTransductionA

    tl = Timeline()
    node = Node("n1", tl)
    mem_array = MemoryArray("mem", tl)
    mem_array.owner = node

    # 通常ケース（0 < product < 1）
    eqt = EqTransductionA(node, "eg_eqt", "m", "n2", mem_array[0], eta_source=0.8, eta_dest=0.5)
    assert pytest.approx(eqt.effective_eta) == pytest.approx(0.4)

    # 上限を超えるケース（>1）は 1.0 にクリップ
    eqt2 = EqTransductionA(node, "eg_eqt2", "m", "n2", mem_array[0], eta_source=2.0, eta_dest=2.0)
    assert eqt2.effective_eta == 1.0

    # 負の値（理論上はありえないが、安全のため 0 にクリップしておく）
    eqt3 = EqTransductionA(node, "eg_eqt3", "m", "n2", mem_array[0], eta_source=-1.0, eta_dest=0.5)
    assert eqt3.effective_eta == 0.0


def test_eqt_entanglement_succeed_respects_qt_gate(monkeypatch):
    """_entanglement_succeed が EQT 用ゲート結果に従って succeed/fail を呼び分けることを確認。"""
    from sequence.kernel.timeline import Timeline
    from sequence.topology.node import Node
    from sequence.components.memory import MemoryArray
    from sequence.entanglement_management.generation.qt_eqt import EqTransductionA
    from sequence.entanglement_management.generation.barret_kok import BarretKokA

    tl = Timeline()
    node = Node("n1", tl)
    mem_array = MemoryArray("mem", tl)
    mem_array.owner = node

    eqt = EqTransductionA(node, "eg_eqt", "m", "n2", mem_array[0])

    called = {"succeed": False, "fail": False}

    # BarrettKokA 側の _entanglement_succeed をスタブ化して呼び出し有無を記録
    def fake_super_succeed(self):
        called["succeed"] = True

    # EqTransductionA 側の _entanglement_fail もスタブ化
    def fake_fail(self):
        called["fail"] = True

    monkeypatch.setattr(BarretKokA, "_entanglement_succeed", fake_super_succeed, raising=False)
    monkeypatch.setattr(EqTransductionA, "_entanglement_fail", fake_fail, raising=False)

    # ケース1: ゲートが True の場合 → succeed が呼ばれ、fail は呼ばれない
    monkeypatch.setattr(EqTransductionA, "_qt_success_gate", lambda self: True, raising=False)
    called["succeed"] = False
    called["fail"] = False
    eqt._entanglement_succeed()
    assert called["succeed"] is True
    assert called["fail"] is False

    # ケース2: ゲートが False の場合 → fail が呼ばれ、succeed は呼ばれない
    monkeypatch.setattr(EqTransductionA, "_qt_success_gate", lambda self: False, raising=False)
    called["succeed"] = False
    called["fail"] = False
    eqt._entanglement_succeed()
    assert called["succeed"] is False
    assert called["fail"] is True
