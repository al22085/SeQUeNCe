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
# Helper utilities / dummy classes for tests
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
# Transmon.generation() のテスト
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
# EmittingProtocol + Transducer (up-conversion) のテスト
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
# DownConversionProtocol のテスト
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
