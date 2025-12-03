# sequence/entanglement_management/generation/qt_dq.py

from typing import TYPE_CHECKING, Any

from .generation_base import EntanglementGenerationA, EntanglementGenerationB
from .barret_kok import BarretKokA, BarretKokB
from ...constants import DQT

if TYPE_CHECKING:
    from ...components.memory import Memory
    from ...topology.node import Node, BSMNode


@EntanglementGenerationA.register(DQT)
class DirectQTA(BarretKokA):
    """QT (Direct Quantum Transduction) 用の EntanglementGenerationA.

    今の段階では Barrett-KokA のロジックを継承しつつ、
    - protocol_type を DQT にする
    - 外部から渡された `qt_emitter` の start() を使って実際の送信を行う（あれば）
    """

    def __init__(self, owner: "Node", name: str, middle: str, other: str, memory: "Memory", **kwargs: Any):
        # BarretKokA は kwargs が残っていると ValueError を投げるので、
        # ここで QT 関連だけ抜いてから super().__init__ に渡す
        self.qt_emitter = kwargs.pop("qt_emitter", None)

        super().__init__(owner, name, middle, other, memory, **kwargs)
        self.protocol_type = DQT

    def emit_event(self) -> None:
        """DQT 版 emit_event.

        - ent_round==1 のときは |+> 準備（BK と同じ）
        - qt_emitter があれば qt_emitter.start() を呼ぶ
        - なければ BK のデフォルト動作（memory.excite）にフォールバック
        """

        # 1ラウンド目は BK と同じく |+> 準備
        if self.ent_round == 1:
            self.memory.update_state(self._plus_state)

        if self.qt_emitter is not None:
            # QT ハードウェアに実際の送信を任せる
            self.qt_emitter.start()
        else:
            # まだ QT ハードウェアがないケースでは BK の挙動に戻す
            # （memory.excite(self.middle) を呼ぶ）
            super().emit_event()


@EntanglementGenerationB.register(DQT)
class DirectQTB(BarretKokB):
    """QT (Direct Quantum Transduction) 用の EntanglementGenerationB.

    現時点では Barrett-KokB のロジックをそのまま継承しつつ、
    protocol_type を DQT に設定するだけ。
    """

    def __init__(self, owner: "BSMNode", name: str, others: list[str]):
        super().__init__(owner, name, others)
        self.protocol_type = DQT
