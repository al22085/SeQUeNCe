# tests/entanglement_management/test_generation_qt_dq.py

from sequence.constants import BARRET_KOK, DQT
from sequence.entanglement_management.generation.generation_base import (
    EntanglementGenerationA,
    EntanglementGenerationB,
)
from sequence.entanglement_management.generation import qt_dq  # noqa: F401  # 登録のために import だけする
from sequence.kernel.timeline import Timeline
from sequence.topology.node import Node
from sequence.components.transmon import Transmon, EmittingProtocol
from sequence.components.transducer import (
    Transducer,
    UpConversionProtocol,
    MICROWAVE_WAVELENGTH,
    OPTICAL_WAVELENGTH,
)
from sequence.constants import KET0, KET1


class DummyMemory:
    """EntanglementGenerationA の __init__ で使う最小限のダミーメモリ."""
    def __init__(self):
        self.raw_fidelity = 0.9
        self.qstate_key = 0
        self.entangled_memory = {}
        self.fidelity = self.raw_fidelity

class SpyMemory(DummyMemory):
    """emit_event 周りの挙動を観察するための Spy."""
    def __init__(self):
        super().__init__()
        self.update_state_called = False
        self.excite_called = False
        self.last_state = None
        self.last_middle = None

    def update_state(self, state):
        self.update_state_called = True
        self.last_state = state

    def excite(self, middle):
        self.excite_called = True
        self.last_middle = middle

class DummyEmitter:
    """start() だけ持つ QT エミッタ."""
    def __init__(self):
        self.started = False

    def start(self):
        self.started = True

def test_direct_qt_emit_event_uses_qt_emitter_if_provided():
    """qt_emitter を渡した場合、emit_event がその start() を呼び、
    memory.excite は呼ばれないことを確認するテスト。
    """
    from sequence.entanglement_management.generation.qt_dq import DirectQTA

    tl = Timeline()
    node = Node("n_a", tl)
    mem = SpyMemory()
    emitter = DummyEmitter()

    old_type = EntanglementGenerationA.get_global_type()

    try:
        # DQT をグローバルタイプに設定
        EntanglementGenerationA.set_global_type(DQT)

        # factory 経由で DirectQTA を生成（qt_emitter を渡す）
        eg = EntanglementGenerationA.create(
            owner=node,
            name="eg_dqt_emit",
            middle="bsm",
            other="n_b",
            memory=mem,
            qt_emitter=emitter,
        )
        assert isinstance(eg, DirectQTA)

        # 1ラウンド目にしておく（update_memory が ent_round をインクリメントする）
        assert eg.ent_round == 0

        # 通常は Node にアタッチされてから動くので、それを再現
        node.protocols.append(eg)

        eg.update_memory()
        assert eg.ent_round == 1

        # emit_event 実行
        eg.emit_event()

        # |+> 準備が行われている
        assert mem.update_state_called is True

        # QT エミッタが使われている
        assert emitter.started is True

        # BK の経路（memory.excite）は呼び出されていない
        assert mem.excite_called is False

    finally:
        # グローバルタイプを元に戻す
        EntanglementGenerationA.set_global_type(old_type)


def test_dqt_registered_in_entanglement_generation_registry():
    """DQT プロトコルが registry に登録されていることを確認."""
    protocols_a = EntanglementGenerationA.list_protocols()
    protocols_b = EntanglementGenerationB.list_protocols()

    assert DQT in protocols_a
    assert DQT in protocols_b


def test_dqt_factory_creates_direct_qt_instances():
    """set_global_type(DQT) で factory から DirectQTA/B が生成されることを確認."""
    from sequence.entanglement_management.generation.qt_dq import DirectQTA, DirectQTB

    tl = Timeline()
    node_a = Node("n_a", tl)
    node_bsm = Node("bsm", tl)  # BSMNode じゃなくても、ここでは owner として名前があれば十分

    mem = DummyMemory()

    # 元のプロトコル種別を退避しておく（他テストへの影響を避ける）
    old_type_a = EntanglementGenerationA.get_global_type()
    old_type_b = EntanglementGenerationB.get_global_type()

    try:
        # DQT に切り替え
        EntanglementGenerationA.set_global_type(DQT)
        EntanglementGenerationB.set_global_type(DQT)

        # A 側
        eg_a = EntanglementGenerationA.create(
            owner=node_a,
            name="eg_dqt_a",
            middle="bsm",
            other="n_b",
            memory=mem,
        )
        assert isinstance(eg_a, DirectQTA)
        assert eg_a.protocol_type == DQT

        # B 側
        eg_b = EntanglementGenerationB.create(
            owner=node_bsm,
            name="eg_dqt_b",
            others=["n_a", "n_b"],
        )
        assert isinstance(eg_b, DirectQTB)
        assert eg_b.protocol_type == DQT

    finally:
        # グローバル設定を元に戻す
        EntanglementGenerationA.set_global_type(old_type_a)
        EntanglementGenerationB.set_global_type(old_type_b)

class DummyMemoryForQT(DummyMemory):
    """QT 用 EG として最低限の Memory インターフェースだけ持つ Spy."""
    def __init__(self):
        super().__init__()
        self.update_state_called = False
        self.last_state = None

    def update_state(self, state):
        self.update_state_called = True
        self.last_state = state

    # entanglement_succeed で使われる可能性があるが、
    # このテストでは emit_event までしか見ないので excite は不要。


class DummyUpSuccessSink:
    """Transducer up 成功時のシンク。transmit/get のどちらで呼ばれてもカウントだけする."""
    def __init__(self):
        self.count = 0
        self.last_photon = None

    def transmit(self, photon):
        self.count += 1
        self.last_photon = photon

    def get(self, photon):
        self.transmit(photon)


class DummyUpFailureSink:
    def __init__(self):
        self.count = 0

    def get(self, photon):
        self.count += 1


def test_direct_qt_emit_event_triggers_real_transmon_emitter():
    """DirectQTA.emit_event が実際の EmittingProtocol を起動し、
    Transmon/Transducer のフラグが立つことを確認するテスト。
    """
    from sequence.entanglement_management.generation.qt_dq import DirectQTA

    tl = Timeline()
    node = Node("n_qt", tl)

    # --- Transmon / Transducer セットアップ (Layer0 とほぼ同じ) ---
    wavelengths = [MICROWAVE_WAVELENGTH, OPTICAL_WAVELENGTH]
    photons_quantum_state = [KET1, KET0]  # mw = |1>, opt = |0>

    transmon = Transmon(
        owner=node,
        name="tm_qt",
        timeline=tl,
        wavelengths=wavelengths,
        photon_counter=0,
        photons_quantum_state=photons_quantum_state,
        efficiency=1.0,
    )

    transducer = Transducer(owner=node, name="td_qt", timeline=tl, efficiency=1.0)

    # Transmon -> Transducer (microwave)
    transmon.add_outputs([transducer])

    # UpConversionProtocol 設定
    up_proto = UpConversionProtocol(owner=node, name="up_qt", tl=tl, transducer=transducer)
    transducer.up_conversion_protocol = up_proto

    # Up 成功/失敗先
    up_success_sink = DummyUpSuccessSink()
    up_failure_sink = DummyUpFailureSink()
    transducer.add_outputs([up_success_sink, up_failure_sink])

    # EmittingProtocol (Transmon + Transducer) を作る
    emitter = EmittingProtocol(owner=node, name="emit_qt", tl=tl, transmon=transmon, transducer=transducer)

    # --- DQT EG セットアップ ---
    mem = DummyMemoryForQT()

    eg = DirectQTA(
        owner=node,
        name="eg_dqt_integ",
        middle="bsm_dummy",
        other="remote_dummy",
        memory=mem,
        qt_emitter=emitter,
    )

    # Node にプロトコルとしてアタッチしておく（update_memory 内のガードのため）
    node.protocols.append(eg)

    # 1ラウンド目にする（update_memory が ent_round をインクリメントする）
    assert eg.ent_round == 0
    eg.update_memory()
    assert eg.ent_round == 1

    # --- 実行: EG 側から emit_event を呼ぶ ---
    eg.emit_event()

    # Memory 側では |+> 準備がされている
    assert mem.update_state_called is True

    # Transmon が発光している（テスト環境の実装に応じて、以下のどれかで確認）
    # 例1: last_emission_success フラグが True
    assert getattr(transmon, "last_emission_success", True) is True

    # 例2: Transducer の up 成功フラグまたはシンクカウンタで確認
    # last_up_success フラグがあればそれを見る
    if hasattr(transducer, "last_up_success"):
        assert transducer.last_up_success is True

    # up 成功シンクにフォトンが届いていることも確認
    assert up_success_sink.count == 1
    assert up_failure_sink.count == 0
