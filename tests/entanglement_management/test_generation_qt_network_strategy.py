"""EG 戦略のグローバル設定が Rule 経由のプロトコル生成にも反映されることを確認するテスト。"""

import sequence.entanglement_management.generation.qt_eqt  # noqa: F401  # EQT を registry に登録

from sequence.constants import EQT
from sequence.entanglement_management.generation import (
    EntanglementGenerationA,
    EntanglementGenerationB,
)
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.kernel.timeline import Timeline
from sequence.network_management.reservation import (
    Reservation,
    eg_rule_action1,
    eg_rule_condition,
)
from sequence.resource_management.rule_manager import Rule
from sequence.topology.node import QuantumRouter, BSMNode


def test_rule_generated_protocols_respect_global_eqt():
    """RuleManager 経由で生成された EG プロトコルが protocol_type=EQT になることを検証。"""
    old_a = EntanglementGenerationA.get_global_type()
    old_b = EntanglementGenerationB.get_global_type()
    try:
        # 先にグローバルタイプを EQT に設定しておく
        EntanglementGenerationA.set_global_type(EQT)
        EntanglementGenerationB.set_global_type(EQT)

        tl = Timeline()
        e0 = QuantumRouter("e0", tl, memo_size=1, seed=0)
        e1 = QuantumRouter("e1", tl, memo_size=1, seed=1)
        m0 = BSMNode("m0", tl, [e0.name, e1.name], seed=2)

        # BSM 対応表とチャネルを最低限セットアップ
        e0.add_bsm_node(m0.name, e1.name)
        e1.add_bsm_node(m0.name, e0.name)
        QuantumChannel("qc_e0_m0", tl, 0, 1e3).set_ends(e0, m0.name)
        QuantumChannel("qc_e1_m0", tl, 0, 1e3).set_ends(e1, m0.name)
        for src in (e0, e1, m0):
            for dst in (e0, e1, m0):
                if src.name == dst.name:
                    continue
                ClassicalChannel(f"cc_{src.name}_{dst.name}", tl, 1e3, delay=1e9).set_ends(src, dst.name)

        # Responder 側（index=1）の EG ルールを 1 つだけ作る（REQUEST を飛ばさず待ち受けにする）
        reservation = Reservation(e0.name, e1.name, start_time=0, end_time=int(1e9), memory_size=1, fidelity=0.9)
        path = [e0.name, e1.name]
        rsvp = e1.network_manager.protocol_stack[-1]
        rsvp.timecards[0].add(reservation)

        action_args = {"mid": e1.map_to_middle_node[e0.name], "path": path, "index": 1}
        condition_args = {"memory_indices": [0]}
        rule = Rule(10, eg_rule_action1, eg_rule_condition, action_args, condition_args)
        rule.set_reservation(reservation)

        e1.resource_manager.load(rule)

        tl.init()
        tl.run()

        # 生成されたプロトコル（rule.protocols や waiting/pending に残るもの）が EQT か確認
        protocols = (
            list(rule.protocols)
            + list(e1.resource_manager.waiting_protocols)
            + list(e1.resource_manager.pending_protocols)
            + list(e1.protocols)
        )
        assert protocols, "ルール適用で少なくとも 1 つはプロトコルが生成される想定"
        assert all(getattr(p, "protocol_type", None) == EQT for p in protocols)
    finally:
        # ほかのテストへの影響を避けるためグローバル設定を戻す
        EntanglementGenerationA.set_global_type(old_a)
        EntanglementGenerationB.set_global_type(old_b)
