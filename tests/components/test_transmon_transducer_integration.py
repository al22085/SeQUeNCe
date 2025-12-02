"""
Integration tests for Transmon + Transducer hardware components.

These tests verify:
- emission from Transmon via EmittingProtocol
- up/down conversion behavior in Transducer
- success/failure flags exposed to upper layers
"""

from __future__ import annotations

import numpy as np

from sequence.constants import KET0, KET1
from sequence.kernel.timeline import Timeline
from sequence.topology.node import Node
from sequence.components.photon import Photon
from sequence.components.transmon import Transmon, EmittingProtocol
from sequence.components.transducer import (
    Transducer,
    UpConversionProtocol,
    DownConversionProtocol,
    MICROWAVE_WAVELENGTH,
    OPTICAL_WAVELENGTH,
)


# =============================================================================
# Common helpers / dummy classes
# =============================================================================


def _make_timeline_and_node(name: str = "n1") -> tuple[Timeline, Node]:
    """テスト用の Timeline と Node を生成する小さなユーティリティ."""
    tl = Timeline()
    node = Node(name, tl)
    return tl, node


class DummyTransmitSink:
    """transmit(photon) を呼ばれた Photon を保存するだけのダミー送信先."""

    def __init__(self) -> None:
        self.transmitted_photon: Photon | None = None

    def transmit(self, photon: Photon) -> None:
        self.transmitted_photon = photon


class DummyGetSink:
    """get(photon) を呼ばれた Photon を保存するだけのダミー受信先."""

    def __init__(self) -> None:
        self.received_photon: Photon | None = None

    def get(self, photon: Photon, **_: object) -> None:
        self.received_photon = photon


class DummyTransducer(Transducer):
    """
    Transmon から Photon を受け取り、そのまま UpConversionProtocol を呼ぶテスト用 Transducer.

    - receive_photon_from_transmon(...) が呼ばれたこと
    - 受け取った Photon が up-conversion に渡されること
    をテストしやすくするため、Photon の参照を保持する。
    """

    def __init__(self, owner: Node, name: str, timeline: Timeline, efficiency: float = 1.0) -> None:
        super().__init__(owner, name, timeline, efficiency)
        # テストで直接中身を確認したいので、Transmon から受け取った Photon を保持
        self.received_from_transmon: Photon | None = None

    def receive_photon_from_transmon(self, photon: Photon) -> None:
        """
        Transmon から Photon を受け取ったときの動作.

        本番コードと同様に up_conversion_protocol.convert を呼ぶが、
        追加で self.received_from_transmon に Photon の参照を保存しておく。
        """
        self.received_from_transmon = photon
        # UpConversionProtocol が Photon の波長や量子状態を変更してくれることを期待
        self.up_conversion_protocol.convert(photon)


# =============================================================================
# Transmon.generation() unit tests
# =============================================================================


def test_transmon_generation_sets_input_state_and_returns_microwave_photon() -> None:
    """
    Transmon.generation() が 2量子状態を正しくセットし、
    戻り値としてマイクロ波モードの Photon を返すことを確認する。
    """
    tl, node = _make_timeline_and_node()

    # wavelengths[0]: マイクロ波, wavelengths[1]: 光
    wavelengths = [999_308, 1550]
    # mw = |1>, opt = |0>
    photons_quantum_state = [KET1, KET0]

    transmon = Transmon(
        owner=node,
        name="t1",
        timeline=tl,
        wavelengths=wavelengths,
        photon_counter=0,
        photons_quantum_state=photons_quantum_state,
        efficiency=1.0,
    )

    photon = transmon.generation()

    # --- 2量子状態 (mw ⊗ opt) が正しく内部にセットされているか -------------------
    expected_state = np.kron(photons_quantum_state[0], photons_quantum_state[1])
    assert np.allclose(transmon.input_quantum_state, expected_state)

    # --- 戻り値の Photon がマイクロ波モード (wavelengths[0]) を表しているか --------
    assert isinstance(photon, Photon)
    assert photon.wavelength == wavelengths[0]
    # 量子状態が何らかのベクトルとして与えられていることだけを確認
    assert photon.quantum_state is not None


# =============================================================================
# EmittingProtocol + Transducer (up-conversion) unit tests
# =============================================================================


def test_emitting_protocol_success_and_flag() -> None:
    """
    EmittingProtocol による発光が成功した場合に、
    - Transmon.last_emission_success
    - Transducer.last_up_success
    が True になること、および up-conversion の出力 Photon が
    光モードになっていることを確認する。
    """
    tl, node = _make_timeline_and_node()

    wavelengths = [MICROWAVE_WAVELENGTH, OPTICAL_WAVELENGTH]
    photons_quantum_state = [KET1, KET0]

    transmon = Transmon(
        owner=node,
        name="t1",
        timeline=tl,
        wavelengths=wavelengths,
        photon_counter=0,
        photons_quantum_state=photons_quantum_state,
        efficiency=1.0,
    )
    transducer = DummyTransducer(node, "d1", tl, efficiency=1.0)

    # 成功パス / 失敗パス用のシンプルな出力先（チャネル）を設定
    success_sink = DummyTransmitSink()
    failure_sink = DummyGetSink()
    transducer.add_outputs([success_sink, failure_sink])

    # Up-conversion protocol を Transducer に紐づけ
    up_proto = UpConversionProtocol(node, "up", tl, transducer)
    transducer.up_conversion_protocol = up_proto

    # Transmon -> Transducer への接続
    transmon.add_outputs([transducer])

    # EmittingProtocol のセットアップ
    emit_proto = EmittingProtocol(node, "emit", tl, transmon, transducer)

    # 実際にプロトコルを開始
    emit_proto.start()

    # --- フラグの確認 ---------------------------------------------------------
    # 発光が成功していること
    assert transmon.last_emission_success is True
    # up-conversion が成功していること
    assert transducer.last_up_success is True

    # 成功パスの送信先に Photon が届いていること
    assert isinstance(success_sink.transmitted_photon, Photon)

    # DummyTransducer.received_from_transmon は up-conversion 後の Photon を指す想定
    # Photon は光モード (OPTICAL_WAVELENGTH) になっているはず
    assert transducer.received_from_transmon is not None
    assert transducer.received_from_transmon.wavelength == OPTICAL_WAVELENGTH


def test_emitting_protocol_failure_flag() -> None:
    """
    EmittingProtocol による発光が失敗した場合に、
    Transmon.last_emission_success が False になることを確認する。

    （up-conversion 側が呼ばれない or last_up_success が False のまま
      などの挙動は EmittingProtocol/Transducer 実装に依存させる）
    """
    tl, node = _make_timeline_and_node()

    wavelengths = [MICROWAVE_WAVELENGTH, OPTICAL_WAVELENGTH]
    photons_quantum_state = [KET1, KET0]

    # Transmon 側の効率を 0.0 にして発光が必ず失敗するようにする
    transmon = Transmon(
        owner=node,
        name="t1",
        timeline=tl,
        wavelengths=wavelengths,
        photon_counter=0,
        photons_quantum_state=photons_quantum_state,
        efficiency=0.0,
    )
    transducer = DummyTransducer(node, "d1", tl, efficiency=1.0)

    # Transmon -> Transducer の接続のみ（up-conversion の成否には依存しない）
    transmon.add_outputs([transducer])

    up_proto = UpConversionProtocol(node, "up", tl, transducer)
    transducer.up_conversion_protocol = up_proto

    emit_proto = EmittingProtocol(node, "emit", tl, transmon, transducer)
    emit_proto.start()

    # 発光に失敗しているため False であること
    assert transmon.last_emission_success is False
    # up_conversion が呼ばれたかどうかはこのテストでは拘束しない


# =============================================================================
# DownConversionProtocol unit tests
# =============================================================================


def test_down_conversion_success_and_failure() -> None:
    """
    DownConversionProtocol.convert() が

    - 成功ケース: last_down_success=True となり、
      成功パスの出力先にマイクロ波モードの Photon が送られる
    - 失敗ケース: last_down_success=False となり、
      失敗パスの出力先に元の（光モードの）Photon が送られる

    という振る舞いをすることを確認する。
    """
    tl, node = _make_timeline_and_node()
    transducer = Transducer(node, "d1", tl, efficiency=1.0)

    # 成功パス / 失敗パス用のシンプルな受信先
    success_sink = DummyGetSink()
    failure_sink = DummyGetSink()
    transducer.add_outputs([success_sink, failure_sink])

    # Down-conversion protocol を Transducer に紐づけ
    down_proto = DownConversionProtocol(node, "down", tl, transducer)
    transducer.down_conversion_protocol = down_proto

    # -------------------------------------------------------------------------
    # 成功ケース: efficiency=1.0
    # -------------------------------------------------------------------------
    photon = Photon("p", tl, wavelength=OPTICAL_WAVELENGTH)

    down_proto.convert(photon)

    # down-conversion が成功したフラグ
    assert transducer.last_down_success is True
    # 成功パスの受信先に Photon が届いていること
    assert success_sink.received_photon is photon
    # Photon はマイクロ波モードに変換されているはず
    assert photon.wavelength == MICROWAVE_WAVELENGTH

    # -------------------------------------------------------------------------
    # 失敗ケース: efficiency=0.0
    # -------------------------------------------------------------------------
    transducer.efficiency = 0.0
    success_sink.received_photon = None
    failure_sink.received_photon = None

    photon2 = Photon("p2", tl, wavelength=OPTICAL_WAVELENGTH)

    down_proto.convert(photon2)

    # down-conversion が失敗したフラグ
    assert transducer.last_down_success is False
    # 失敗パスの受信先に Photon が届いていること
    assert failure_sink.received_photon is photon2
    # 失敗時は波長が変わらない（光モードのまま）こと
    assert photon2.wavelength == OPTICAL_WAVELENGTH


# ============================================================
# 1-link Direct Quantum Transduction (DQT) integration tests
# ============================================================


class DummyChannel:
    """
    簡易光チャネル。

    transmit(photon) が呼ばれたら、その場で receiver.get(photon) を呼ぶだけ。
    中継ノードや遅延などは無視して、「配線が正しいか」の確認にフォーカスする。
    """

    def __init__(self) -> None:
        self.receiver = None
        self.transmitted_photons: list[Photon] = []

    def add_receiver(self, receiver) -> None:
        self.receiver = receiver

    def transmit(self, photon: Photon) -> None:
        assert self.receiver is not None, "DummyChannel has no receiver"
        self.transmitted_photons.append(photon)
        self.receiver.get(photon)


class DummySink:
    """失敗パス用のダミーシンク。get が呼ばれた photon を全部保存する。"""

    def __init__(self) -> None:
        self.photons: list[Photon] = []

    def get(self, photon: Photon) -> None:
        self.photons.append(photon)


def build_direct_qt_link(
    eff_transmon: float = 1.0,
    eff_up: float = 1.0,
    eff_down: float = 1.0,
):
    """
    1 本の Direct Quantum Transduction (DQT) ルートを組み立てて、
    関連オブジェクトを dict で返すユーティリティ。

    n1: 送信ノード
      Transmon(tx_transmon) --(EmittingProtocol)--> Transducer(tx_transducer, UpConversion)

    n2: 受信ノード
      Transducer(rx_transducer, DownConversion) --> Transmon(rx_transmon)

    中間は DummyChannel:
      tx_transducer 成功ポート -> DummyChannel -> rx_transducer
      tx_transducer 失敗ポート -> up_fail_sink
      rx_transducer 失敗ポート -> down_fail_sink
    """

    tl = Timeline()
    n1 = Node("n1", tl)
    n2 = Node("n2", tl)

    wavelengths = [MICROWAVE_WAVELENGTH, OPTICAL_WAVELENGTH]
    photons_quantum_state = [KET1, KET0]

    # -------- 送信側 --------
    tx_transmon = Transmon(
        owner=n1,
        name="t_tx",
        timeline=tl,
        wavelengths=wavelengths,
        photon_counter=0,
        photons_quantum_state=photons_quantum_state,
        efficiency=eff_transmon,
    )
    tx_transducer = Transducer(n1, "d_tx", tl, efficiency=eff_up)

    # -------- 受信側 --------
    rx_transmon = Transmon(
        owner=n2,
        name="t_rx",
        timeline=tl,
        wavelengths=wavelengths,
        photon_counter=0,
        photons_quantum_state=photons_quantum_state,
        efficiency=eff_down,
    )
    rx_transducer = Transducer(n2, "d_rx", tl, efficiency=eff_down)

    # -------- プロトコル --------
    emit_proto = EmittingProtocol(n1, "emit", tl, tx_transmon, tx_transducer)
    up_proto = UpConversionProtocol(n1, "up", tl, tx_transducer)
    down_proto = DownConversionProtocol(n2, "down", tl, rx_transducer)

    tx_transducer.up_conversion_protocol = up_proto
    rx_transducer.down_conversion_protocol = down_proto

    # -------- 配線 --------
    # (1) Tx Transmon -> Tx Transducer
    tx_transmon.add_outputs([tx_transducer])

    # (2) Tx Transducer 成功ポート -> DummyChannel, 失敗ポート -> up_fail_sink
    channel = DummyChannel()
    up_fail_sink = DummySink()
    tx_transducer.add_outputs([channel, up_fail_sink])

    # (3) DummyChannel -> Rx Transducer
    channel.add_receiver(rx_transducer)

    # (4) Rx Transducer 成功ポート -> Rx Transmon, 失敗ポート -> down_fail_sink
    down_fail_sink = DummySink()
    rx_transducer.add_outputs([rx_transmon, down_fail_sink])

    return {
        "timeline": tl,
        "nodes": (n1, n2),
        "tx_transmon": tx_transmon,
        "tx_transducer": tx_transducer,
        "rx_transmon": rx_transmon,
        "rx_transducer": rx_transducer,
        "emit_proto": emit_proto,
        "up_fail_sink": up_fail_sink,
        "down_fail_sink": down_fail_sink,
        "channel": channel,
    }


def test_direct_qt_link_success_all_eff_1() -> None:
    """Transmon・Up/Down すべて効率 1 のとき、受信 Transmon が必ず 1 回受信する。"""
    ctx = build_direct_qt_link(eff_transmon=1.0, eff_up=1.0, eff_down=1.0)
    emit_proto = ctx["emit_proto"]
    rx_transmon = ctx["rx_transmon"]

    # 事前に受信していないことを確認
    assert rx_transmon.photon_counter == 0

    emit_proto.start()

    # Emitting -> Up -> Channel -> Down -> Rx Transmon まで通っているはず
    assert rx_transmon.photon_counter == 1
    assert ctx["up_fail_sink"].photons == []
    assert ctx["down_fail_sink"].photons == []


def test_direct_qt_link_failure_in_up_conversion() -> None:
    """Up-conversion 効率 0 のとき、受信 Transmon には届かず up_fail_sink に流れる。"""
    ctx = build_direct_qt_link(eff_transmon=1.0, eff_up=0.0, eff_down=1.0)
    emit_proto = ctx["emit_proto"]
    rx_transmon = ctx["rx_transmon"]
    up_fail_sink = ctx["up_fail_sink"]

    emit_proto.start()

    assert rx_transmon.photon_counter == 0
    assert len(up_fail_sink.photons) == 1


def test_direct_qt_link_failure_in_down_conversion() -> None:
    """Down-conversion 効率 0 のとき、受信 Transmon には届かず down_fail_sink に流れる。"""
    ctx = build_direct_qt_link(eff_transmon=1.0, eff_up=1.0, eff_down=0.0)
    emit_proto = ctx["emit_proto"]
    rx_transmon = ctx["rx_transmon"]
    down_fail_sink = ctx["down_fail_sink"]

    emit_proto.start()

    assert rx_transmon.photon_counter == 0
    assert len(down_fail_sink.photons) == 1
