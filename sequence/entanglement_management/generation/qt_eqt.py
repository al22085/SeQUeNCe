# sequence/entanglement_management/generation/qt_eqt.py

import random
from typing import TYPE_CHECKING, Any

from .barret_kok import BarretKokA, BarretKokB
from .generation_base import EntanglementGenerationA, EntanglementGenerationB
from ...constants import EQT

if TYPE_CHECKING:
    from ...components.memory import Memory
    from ...topology.node import Node, BSMNode


@EntanglementGenerationA.register(EQT)
class EqTransductionA(BarretKokA):
    def __init__(
        self,
        owner: "Node",
        name: str,
        middle: str,
        other: str,
        memory: "Memory",
        eta_source: float = 1.0,  # 送信側トランスデューサ効率
        eta_dest: float = 1.0,    # 受信側トランスデューサ効率
        **kwargs: Any,
    ):
        # 不明なキーワード引数が来た場合はバグの可能性が高いので明示的にエラーにする
        if kwargs:
            raise ValueError(f"Unexpected keyword arguments for EQT: {kwargs}")

        super().__init__(owner, name, middle, other, memory)

        # EQT 用のパラメータを保存しておく（送信側・受信側トランスデューサ効率）
        self.protocol_type = EQT
        self.eta_source = float(eta_source)  # 送信側トランスデューサ効率
        self.eta_dest = float(eta_dest)      # 受信側トランスデューサ効率

    @property
    def effective_eta(self) -> float:
        """EQT 全体としての有効変換効率 η_eff を返す（0〜1 にクリップ）。"""
        prod = self.eta_source * self.eta_dest
        # 数値の暴走を防ぐため 0〜1 の範囲にクリップする
        if prod < 0.0:
            return 0.0
        if prod > 1.0:
            return 1.0
        return prod

    def _qt_success_gate(self) -> bool:
        """EQT 用の追加成功判定（トランスデューサ効率に基づくベルヌーイ試行）。

        Barrett-Kok の測定結果で一度「成功」と判定されたあとに、
        送信側・受信側トランスデューサの効率 (η_source * η_dest) を掛け合わせた
        有効効率 effective_eta でもう一度コイントスを行う。
        """
        # Node が乱数生成器 get_generator() を持っている場合はシード付き RNG を優先利用（再現性確保のため）
        gen = getattr(self.owner, "get_generator", None)
        if callable(gen):
            rng = gen()
            r = rng.random()
        else:
            # フォールバックとして標準ライブラリの random を使う
            r = random.random()

        return r < self.effective_eta

    def _entanglement_succeed(self) -> None:
        """EQT 用の成功処理。

        - まず Barrett-Kok と同じ条件で「成功」とみなされる
        - その後、transducer の有効効率 effective_eta で追加のフィルタをかける
        """
        if self._qt_success_gate():
            # QT 部分も成功したので、通常の Barrett-Kok 成功処理を実行
            super()._entanglement_succeed()
        else:
            # QT 部分で失敗したとみなし、エンタングルメントは成立しなかった扱いにする
            self._entanglement_fail()


@EntanglementGenerationB.register(EQT)
class EqTransductionB(BarretKokB):
    def __init__(
        self,
        owner: "BSMNode",
        name: str,
        others: list[str],
        **kwargs: Any,
    ):
        # 現段階では Barrett-KokB と同じ挙動をそのまま使う
        if kwargs:
            raise ValueError(f"Unexpected keyword arguments for EQT: {kwargs}")
        super().__init__(owner, name, others)
        self.protocol_type = EQT
