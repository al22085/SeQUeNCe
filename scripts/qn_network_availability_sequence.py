"""Event-driven (SeQUeNCe) network availability on 4-node line (A-R1-R2-B)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List

import numpy as np

# Ensure repo root on sys.path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sequence.constants import BARRET_KOK, DQT, EQT
import sequence.entanglement_management.generation.qt_dq  # noqa: F401
import sequence.entanglement_management.generation.qt_eqt  # noqa: F401
from sequence.entanglement_management.generation import EntanglementGenerationA, EntanglementGenerationB
from sequence.components.optical_channel import QuantumChannel, ClassicalChannel
from sequence.kernel.timeline import Timeline
from sequence.network_management.reservation import eg_rule_action1, eg_rule_action2, eg_rule_condition
from sequence.resource_management.rule_manager import Rule
from sequence.topology.node import QuantumRouter, BSMNode


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Request-level availability using SeQUeNCe on A-R1-R2-B line.")
    p.add_argument("--strategy", choices=["BK", "DQT", "EQT"], default="BK")
    p.add_argument("--arch", choices=["optical", "hybrid"], default="optical")
    p.add_argument("--distance", type=float, default=1e3, help="Per-link distance (m).")
    p.add_argument("--deadline", type=float, default=2e4, help="Timeline stop_time/deadline (ps).")
    p.add_argument("--num-trials", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--eta-source", type=float, default=0.8)
    p.add_argument("--eta-dest", type=float, default=0.8)
    p.add_argument("--dqt-eta-source", type=float, default=1.0)
    p.add_argument("--dqt-eta-dest", type=float, default=0.7)
    p.add_argument("--qt-eff", type=float, default=None, help="Legacy DQT success prob (overrides dqt etas).")
    p.add_argument("--format", choices=["md", "json", "csv"], default="md")
    p.add_argument("--out", type=Path, default=None)
    return p.parse_args()


def set_strategy(proto: str) -> str:
    if proto == "BK":
        pt = BARRET_KOK
    elif proto == "DQT":
        pt = DQT
    elif proto == "EQT":
        pt = EQT
    else:
        raise ValueError(proto)
    EntanglementGenerationA.set_global_type(pt)
    EntanglementGenerationB.set_global_type(pt)
    return pt


def install_pair(tl: Timeline, n1: QuantumRouter, n2: QuantumRouter, bsm: BSMNode, link_name: str, dqt_emitter_prob: float | None, eta_source: float, eta_dest: float):
    # add BSM mapping and channels
    n1.add_bsm_node(bsm.name, n2.name)
    n2.add_bsm_node(bsm.name, n1.name)
    qc1 = QuantumChannel(f"qc_{link_name}_1", tl, attenuation=2e-4, distance=tl.params.get("distance_override", None) or 0)
    qc2 = QuantumChannel(f"qc_{link_name}_2", tl, attenuation=2e-4, distance=tl.params.get("distance_override", None) or 0)
    qc1.set_ends(n1, bsm.name)
    qc2.set_ends(n2, bsm.name)
    for src in (n1, n2, bsm):
        for dst in (n1, n2, bsm):
            if src.name == dst.name:
                continue
            cc = ClassicalChannel(f"cc_{link_name}_{src.name}_{dst.name}", tl, 1e3, delay=1e9)
            cc.set_ends(src, dst.name)

    def make_rule(router: QuantumRouter, index: int, path: List[str]):
        mem_array = router.components[router.memo_arr_name]
        memory_indices = list(range(len(mem_array.memories)))
        if index > 0:
            condition_args = {"memory_indices": memory_indices}
            action_args = {"mid": router.map_to_middle_node[path[index - 1]], "path": path, "index": index}
            rule = Rule(10, eg_rule_action1, eg_rule_condition, action_args, condition_args)
        else:
            condition_args = {"memory_indices": memory_indices}
            action_args = {"mid": router.map_to_middle_node[path[index + 1]], "path": path, "index": index, "name": router.name, "reservation": None}
            rule = Rule(10, eg_rule_action2, eg_rule_condition, action_args, condition_args)
        return rule

    path = [n1.name, n2.name]
    r1 = make_rule(n1, 0, path)
    r2 = make_rule(n2, 1, path)
    n1.resource_manager.load(r1)
    n2.resource_manager.load(r2)

    orig_create = EntanglementGenerationA.create.__func__
    if EntanglementGenerationA.get_global_type() == EQT:
        def eqt_create(cls, owner, name, middle, other, memory, **kwargs):
            kwargs.setdefault("eta_source", eta_source)
            kwargs.setdefault("eta_dest", eta_dest)
            return orig_create(cls, owner, name, middle, other, memory, **kwargs)
        EntanglementGenerationA.create = classmethod(eqt_create)  # type: ignore
    elif EntanglementGenerationA.get_global_type() == DQT:
        prob = dqt_emitter_prob if dqt_emitter_prob is not None else dqt_eta_source * dqt_eta_dest

        def dqt_create(cls, owner, name, middle, other, memory, **kwargs):
            kwargs.setdefault("qt_emitter", _make_dqt_emitter(owner, memory, middle, prob))
            return orig_create(cls, owner, name, middle, other, memory, **kwargs)
        EntanglementGenerationA.create = classmethod(dqt_create)  # type: ignore


def _make_dqt_emitter(owner, memory, middle: str, success_prob: float):
    class DQEmitter:
        def start(self):
            node = owner
            if node is None:
                node = getattr(getattr(memory, "memory_array", None), "owner", None)
            rng = node.get_generator() if node is not None else np.random.default_rng()
            if rng.random() < success_prob:
                memory.excite(middle)
    return DQEmitter()


def build_network(tl: Timeline, distance: float, dqt_prob: float | None, eta_source: float, eta_dest: float, dqt_eta_source: float, dqt_eta_dest: float):
    # attach distance override to timeline for channel setup
    tl.params["distance_override"] = distance
    A = QuantumRouter("A", tl, memo_size=2)
    R1 = QuantumRouter("R1", tl, memo_size=2)
    R2 = QuantumRouter("R2", tl, memo_size=2)
    B = QuantumRouter("B", tl, memo_size=2)
    bsm01 = BSMNode("bsm01", tl, [A.name, R1.name])
    bsm12 = BSMNode("bsm12", tl, [R1.name, R2.name])
    bsm23 = BSMNode("bsm23", tl, [R2.name, B.name])

    install_pair(tl, A, R1, bsm01, "A_R1", dqt_prob, eta_source, eta_dest)
    install_pair(tl, R1, R2, bsm12, "R1_R2", dqt_prob, eta_source, eta_dest)
    install_pair(tl, R2, B, bsm23, "R2_B", dqt_prob, eta_source, eta_dest)

    return A, R1, R2, B


def run_trial(trial_idx: int, args: argparse.Namespace, pt: str) -> Dict[str, float | bool]:
    tl = Timeline(stop_time=int(args.deadline))
    tl.params = {}
    seed = None if args.seed is None else args.seed + trial_idx
    if seed is not None:
        np.random.seed(seed)
    dqt_prob = args.qt_eff if args.qt_eff is not None else args.dqt_eta_source * args.dqt_eta_dest
    A, R1, R2, B = build_network(tl, args.distance, dqt_prob if pt == DQT else None, args.eta_source, args.eta_dest, args.dqt_eta_source, args.dqt_eta_dest)

    satisfied = {"done": False, "time": None}

    def check_success():
        memA = A.components[A.memo_arr_name].memories
        memR1 = R1.components[R1.memo_arr_name].memories
        memR2 = R2.components[R2.memo_arr_name].memories
        memB = B.components[B.memo_arr_name].memories
        links = [
            any(m.entangled_memory for m in memA),
            any(m.entangled_memory for m in memR1) and any(m.entangled_memory for m in memR2),
            any(m.entangled_memory for m in memB),
        ]
        if all(links):
            satisfied["done"] = True
            satisfied["time"] = tl.now()
            tl.stop()

    original_updates = {}
    for router in (A, R1, R2, B):
        rm = router.resource_manager
        original_updates[rm] = rm.update

        def make_update(orig):
            def update(protocol, memory, state):
                res = orig(protocol, memory, state)
                if state == "ENTANGLED":
                    check_success()
                return res
            return update

        rm.update = make_update(original_updates[rm])  # type: ignore

    tl.init()
    tl.run()

    return {"success": satisfied["done"], "t_success": satisfied["time"]}


def run_trials(args: argparse.Namespace) -> Dict[str, any]:
    pt = set_strategy(args.strategy)
    successes = 0
    times: List[int] = []
    for i in range(args.num_trials):
        res = run_trial(i, args, pt)
        if res["success"]:
            successes += 1
            times.append(res["t_success"])
    availability = successes / args.num_trials if args.num_trials > 0 else 0.0
    mean_t = float(np.mean(times)) if times else None
    return {
        "arch": args.arch,
        "strategy": args.strategy,
        "distance_per_link": args.distance,
        "deadline": args.deadline,
        "num_trials": args.num_trials,
        "satisfied": successes,
        "availability_req": availability,
        "mean_t_success": mean_t,
        "params": {
            "eta_source": args.eta_source,
            "eta_dest": args.eta_dest,
            "dqt_eta_source": args.dqt_eta_source,
            "dqt_eta_dest": args.dqt_eta_dest,
            "qt_eff": args.qt_eff,
        },
    }


def emit(result: Dict[str, any], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(result, indent=2)
    if fmt == "csv":
        headers = ["arch", "strategy", "distance_per_link", "deadline", "num_trials", "satisfied", "availability_req", "mean_t_success"]
        values = [str(result.get(h, "")) for h in headers]
        return ",".join(headers) + "\n" + ",".join(values)
    headers = ["arch", "strategy", "distance_per_link", "deadline", "num_trials", "satisfied", "availability_req", "mean_t_success"]
    row = [
        result.get("arch"),
        result.get("strategy"),
        f"{result.get('distance_per_link')}",
        f"{result.get('deadline')}",
        str(result.get("num_trials")),
        str(result.get("satisfied")),
        f"{result.get('availability_req'):.3f}",
        "N/A" if result.get("mean_t_success") is None else f"{result.get('mean_t_success'):.2f}",
    ]
    return "| " + " | ".join(headers) + " |\n|" + " --- |" * len(headers) + "\n| " + " | ".join(row) + " |"


def main() -> None:
    args = parse_args()
    result = run_trials(args)
    output = emit(result, args.format)
    if args.out:
        args.out.write_text(output)
    print(output)


if __name__ == "__main__":
    main()
