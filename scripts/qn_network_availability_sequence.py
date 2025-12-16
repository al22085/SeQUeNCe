"""Event-driven (SeQUeNCe) network availability on 4-node line (A-R1-R2-B)."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, List, Optional

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
from sequence.network_management.network_manager import StaticRoutingProtocol
from sequence.network_management.reservation import es_rule_actionA, es_rule_actionB
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.app.benchmark_request_app import BenchmarkRequestApp
from sequence.resource_management.memory_manager import MemoryInfo


def sec_to_ps(s: float) -> int:
    return int(round(s * 1e12))


def ps_to_sec(ps: int) -> float:
    return ps / 1e12


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Request-level availability using SeQUeNCe on A-R1-R2-B line.")
    p.add_argument("--strategy", choices=["BK", "DQT", "EQT"], default="BK")
    p.add_argument("--arch", choices=["optical", "hybrid", "custom"], default="optical")
    p.add_argument("--distance", type=float, default=1e3, help="Per-link distance (m). Total path length = 3*distance.")
    p.add_argument("--deadline-mode", choices=["absolute", "scaled"], default="absolute", help="absolute: use deadline-s/ps; scaled: deadline_s = factor * (path_distance / fiber_v). Timeline unit is ps.")
    p.add_argument("--deadline-ps", type=float, default=None, help="Deadline in picoseconds (timeline unit). Used if deadline-mode=absolute or provided explicitly.")
    p.add_argument("--deadline-s", type=float, default=0.1, help="Optional deadline in seconds (overrides ps) when deadline-mode=absolute.")
    p.add_argument("--deadline-factor", type=float, default=20.0, help="Scaled deadline multiplier: deadline_s = factor * (total_distance / fiber_v).")
    p.add_argument("--fiber-v", type=float, default=2e8, help="Fiber group velocity (m/s) for deadline scaling.")
    p.add_argument("--setup-factor", type=float, default=5000.0, help="Multiplier for reservation setup slack (slack = factor * path_distance/fiber_v).")
    p.add_argument("--min-start-delay-s", type=float, default=0.01, help="Minimum start slack in seconds to ensure RSVP setup before start_time.")
    p.add_argument("--num-trials", type=int, default=20)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--eta-source", type=float, default=0.8)
    p.add_argument("--eta-dest", type=float, default=0.8)
    p.add_argument("--dqt-eta-source", type=float, default=1.0)
    p.add_argument("--dqt-eta-dest", type=float, default=0.7)
    p.add_argument("--qt-eff", type=float, default=None, help="Legacy DQT success prob (overrides dqt etas).")
    p.add_argument("--swap-success", type=float, default=1.0, help="Swapping success probability.")
    p.add_argument("--mem-coh-s", type=float, default=None, help="Memory coherence time (s) for all nodes.")
    p.add_argument("--attn", type=float, default=2e-4, help="Fiber attenuation coefficient for quantum channels.")
    p.add_argument("--cc-delay", type=float, default=1e9, help="Classical channel delay (ps).")
    p.add_argument("--fidelity", type=float, default=0.9, help="Requested fidelity threshold for reservation (0<f<=1).")
    p.add_argument("--sanity", choices=["off", "ideal"], default="off", help="ideal forces near-deterministic params (short links, eta=1, low delays).")
    p.add_argument("--debug", action="store_true", help="Print per-trial debug counters (entanglement/swaps/reservations).")
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


def patch_generation(pt: str, eta_source: float, eta_dest: float, dqt_prob: Optional[float]):
    orig_create = EntanglementGenerationA.create.__func__
    if pt == EQT:
        def eqt_create(cls, owner, name, middle, other, memory, **kwargs):
            kwargs.setdefault("eta_source", eta_source)
            kwargs.setdefault("eta_dest", eta_dest)
            return orig_create(cls, owner, name, middle, other, memory, **kwargs)
        EntanglementGenerationA.create = classmethod(eqt_create)  # type: ignore
    elif pt == DQT:
        prob = dqt_prob if dqt_prob is not None else eta_source * eta_dest

        def dqt_create(cls, owner, name, middle, other, memory, **kwargs):
            kwargs.setdefault("qt_emitter", _make_dqt_emitter(owner, memory, middle, prob))
            return orig_create(cls, owner, name, middle, other, memory, **kwargs)
        EntanglementGenerationA.create = classmethod(dqt_create)  # type: ignore
    return orig_create


def restore_generation(orig_create):
    EntanglementGenerationA.create = classmethod(orig_create)


def install_pair(
    tl: Timeline,
    n1: QuantumRouter,
    n2: QuantumRouter,
    bsm: BSMNode,
    link_name: str,
    attn: float,
    distance: float,
    cc_delay: float,
):
    n1.add_bsm_node(bsm.name, n2.name)
    n2.add_bsm_node(bsm.name, n1.name)
    QuantumChannel(f"qc_{link_name}_1", tl, attenuation=attn, distance=distance).set_ends(n1, bsm.name)
    QuantumChannel(f"qc_{link_name}_2", tl, attenuation=attn, distance=distance).set_ends(n2, bsm.name)
    for src in (n1, n2, bsm):
        for dst in (n1, n2, bsm):
            if src.name == dst.name:
                continue
            ClassicalChannel(f"cc_{link_name}_{src.name}_{dst.name}", tl, 1e3, delay=cc_delay).set_ends(src, dst.name)


def build_network(
    tl: Timeline,
    distance: float,
    mem_coh_s: Optional[float],
    swap_success: float,
    attn: float,
    cc_delay: float,
) -> tuple[QuantumRouter, QuantumRouter, QuantumRouter, QuantumRouter]:
    mem_templates = {}
    if mem_coh_s is not None:
        mem_templates = {"MemoryArray": {"coherence_time": mem_coh_s}}
    memo_size = 4
    A = QuantumRouter("A", tl, memo_size=memo_size, component_templates=mem_templates)
    R1 = QuantumRouter("R1", tl, memo_size=memo_size, component_templates=mem_templates)
    R2 = QuantumRouter("R2", tl, memo_size=memo_size, component_templates=mem_templates)
    B = QuantumRouter("B", tl, memo_size=memo_size, component_templates=mem_templates)
    bsm01 = BSMNode("bsm01", tl, [A.name, R1.name])
    bsm12 = BSMNode("bsm12", tl, [R1.name, R2.name])
    bsm23 = BSMNode("bsm23", tl, [R2.name, B.name])

    install_pair(tl, A, R1, bsm01, "A_R1", attn, distance, cc_delay)
    install_pair(tl, R1, R2, bsm12, "R1_R2", attn, distance, cc_delay)
    install_pair(tl, R2, B, bsm23, "R2_B", attn, distance, cc_delay)

    def set_route(router: QuantumRouter, table: dict):
        proto = router.network_manager.protocol_stack[0]
        assert isinstance(proto, StaticRoutingProtocol)
        for dst, hop in table.items():
            proto.update_forwarding_rule(dst, hop)

    set_route(A, {"B": R1.name})
    set_route(R1, {"A": A.name, "B": R2.name})
    set_route(R2, {"A": R1.name, "B": B.name})
    set_route(B, {"A": R2.name})

    nodes = [A, R1, R2, B]
    for src in nodes:
        for dst in nodes:
            if src is dst:
                continue
            if dst.name not in src.cchannels:
                ClassicalChannel(f"cc_line_{src.name}_{dst.name}", tl, 1e3, delay=cc_delay).set_ends(src, dst.name)

    for n in (A, R1, R2, B):
        rsvp = n.network_manager.protocol_stack[1]
        rsvp.set_swapping_success_rate(swap_success)

    return A, R1, R2, B


def is_ab_entangled(A: QuantumRouter, B: QuantumRouter) -> tuple[bool, int]:
    count = 0
    for info in A.resource_manager.memory_manager:
        if info.state == MemoryInfo.ENTANGLED and info.remote_node == B.name:
            count += 1
    return count > 0, count


def compute_window(args: SimpleNamespace, total_distance: float) -> tuple[int, int, float]:
    if args.deadline_mode == "absolute":
        if args.deadline_s is not None:
            deadline_s = args.deadline_s
        elif args.deadline_ps is not None:
            deadline_s = ps_to_sec(int(args.deadline_ps))
        else:
            deadline_s = 0.1
    else:
        deadline_s = args.deadline_factor * (total_distance / args.fiber_v)
    t_prop_s = total_distance / args.fiber_v
    setup_slack_s = max(args.min_start_delay_s, args.setup_factor * t_prop_s)
    start_time_ps = sec_to_ps(setup_slack_s)
    end_time_ps = sec_to_ps(deadline_s)
    if not isinstance(start_time_ps, int) or not isinstance(end_time_ps, int):
        raise ValueError("Reservation times must be int picoseconds.")
    if not (start_time_ps > 0 and end_time_ps > start_time_ps):
        raise ValueError(f"Invalid reservation window: now=0 start={start_time_ps} end={end_time_ps} slack_s={setup_slack_s} deadline_s={deadline_s}")
    return start_time_ps, end_time_ps, setup_slack_s


def run_trial(
    trial_idx: int,
    args: SimpleNamespace,
    pt: str,
    start_time_ps: int,
    end_time_ps: int,
) -> Dict[str, float | bool | int | None]:
    tl = Timeline(stop_time=end_time_ps)
    seed = None if args.seed is None else args.seed + trial_idx
    if seed is not None:
        np.random.seed(seed)

    A, R1, R2, B = build_network(
        tl,
        args.distance,
        args.mem_coh_s,
        args.swap_success,
        args.attn,
        args.cc_delay,
    )

    success_time = {"t": None}

    def record_delivery(info):
        if info.remote_node == B.name and success_time["t"] is None:
            success_time["t"] = tl.now()
            success_time["ab_count"] = success_time.get("ab_count", 0) + 1
            tl.stop()

    appA = BenchmarkRequestApp(A, hold_memories=True, on_delivery=record_delivery)
    appB = BenchmarkRequestApp(B, hold_memories=True)

    neighbor_map = {
        A.name: {R1.name},
        R1.name: {A.name, R2.name},
        R2.name: {R1.name, B.name},
        B.name: {R2.name},
    }

    def link_key(a: str, b: str) -> str:
        return " - ".join(sorted([a, b]))

    dbg_counts = {
        "entangled_total": 0,
        "link_counts": defaultdict(int),
        "swap_events": 0,
        "swap_rules_created": defaultdict(int),
        "ab_pairs_at_r2": 0,
        "swap_rule_mem_counts": defaultdict(list),
        "pair_counts": defaultdict(int),
        "ab_pairs_found": 0,
        "stage1_swaps": 0,
        "stage2_swaps": 0,
    }

    for node in (A, R1, R2, B):
        rsvp = node.network_manager.protocol_stack[1]
        orig_load_rules = rsvp.load_rules

        def load_rules_wrapper(rules, reservation, _orig=orig_load_rules, _name=node.name):
            for r in rules:
                if getattr(r, "action", None) in (es_rule_actionA, es_rule_actionB):
                    r.priority = 0
                    dbg_counts["swap_rules_created"][_name] += 1
                    mems = r.condition_args.get("memory_indices", [])
                    dbg_counts["swap_rule_mem_counts"][_name].append(list(mems))
                    if args.debug:
                        print(json.dumps({"node": _name, "swap_rule_mems": list(mems)}))
            return _orig(rules, reservation)

        rsvp.load_rules = load_rules_wrapper  # type: ignore

    def make_update_wrapper(rm, node_name: str):
        orig_update = rm.update
        debug_limit = {"count": 0}

        def wrapper(protocol, memory, state):
            orig_update(protocol, memory, state)
            if state == MemoryInfo.ENTANGLED:
                info = rm.memory_manager.get_info_by_memory(memory)
                remote = info.remote_node
                dbg_counts["entangled_total"] += 1
                if remote is not None:
                    dbg_counts["link_counts"][link_key(node_name, remote)] += 1
                    pair = tuple(sorted([node_name, remote]))
                    dbg_counts["pair_counts"][pair] += 1
                    if remote not in neighbor_map.get(node_name, set()):
                        dbg_counts["swap_events"] += 1
                        if pair == tuple(sorted([A.name, B.name])):
                            dbg_counts["stage2_swaps"] += 1
                        else:
                            dbg_counts["stage1_swaps"] += 1
                    if success_time["t"] is None and pair == tuple(sorted([A.name, B.name])):
                        success_time["t"] = tl.now()
                        dbg_counts["ab_pairs_found"] += 1
                        tl.stop()
                    if getattr(args, "debug", False) and node_name == "R2" and remote not in neighbor_map.get(node_name, set()) and debug_limit["count"] < 5:
                        debug_limit["count"] += 1
                        print(json.dumps({"event": "r2_entangled", "mem": memory.name, "remote": remote, "time_ps": tl.now(), "state_after": rm.memory_manager.get_info_by_memory(memory).state}))
                    if getattr(args, "debug", False) and node_name == "R2" and remote == B.name and debug_limit["count"] < 10:
                        debug_limit["count"] += 1
                        print(json.dumps({"event": "r2_entangled_B", "mem": memory.name, "remote": remote, "time_ps": tl.now(), "state_after": rm.memory_manager.get_info_by_memory(memory).state}))
                # track if R2 has A-B pair at any time
                if node_name == "R2":
                    remotes = {info.remote_node for info in rm.memory_manager if info.state == MemoryInfo.ENTANGLED}
                    if getattr(args, "debug", False) and debug_limit["count"] < 10:
                        print(json.dumps({"event": "r2_remote_set", "remotes": list(remotes), "time_ps": tl.now()}))
                    if {"A", "B"}.issubset(remotes):
                        dbg_counts["ab_pairs_at_r2"] += 1
        return wrapper

    for node in (A, R1, R2, B):
        node.resource_manager.update = make_update_wrapper(node.resource_manager, node.name)  # type: ignore

    appA.start(B.name, start_t=start_time_ps, end_t=end_time_ps, memo_size=2, fidelity=args.fidelity)

    tl.init()
    tl.run()

    # ensure we capture AB if created near the end
    if success_time["t"] is None:
        has_ab, ab_cnt = is_ab_entangled(A, B)
        if has_ab:
            success_time["t"] = tl.now()
            dbg_counts["ab_pairs_found"] += ab_cnt
    else:
        dbg_counts["ab_pairs_found"] += success_time.get("ab_count", 0)

    accepted_res = {n.name: len(n.network_manager.protocol_stack[1].accepted_reservations) for n in (A, R1, R2, B)}
    dbg_counts["link_counts"] = dict(dbg_counts["link_counts"])
    has_ab_at_r2 = False
    for info in R2.resource_manager.memory_manager:
        if info.state == MemoryInfo.ENTANGLED and info.remote_node in (A.name, B.name):
            other = None
            for info2 in R2.resource_manager.memory_manager:
                if info2 is info:
                    continue
                if info2.state == MemoryInfo.ENTANGLED and {info.remote_node, info2.remote_node} == {A.name, B.name}:
                    has_ab_at_r2 = True
                    break
        if has_ab_at_r2:
            break
    if has_ab_at_r2:
        dbg_counts["ab_pairs_at_r2"] += 1

    return {
        "success": success_time["t"] is not None,
        "t_success": success_time["t"],
        "dbg": {
            "entangled_total": dbg_counts["entangled_total"],
            "link_counts": dbg_counts["link_counts"],
            "swap_events": dbg_counts["swap_events"],
            "swap_rules_created": {k: int(v) for k, v in dbg_counts["swap_rules_created"].items()},
            "ab_pairs_at_r2": dbg_counts["ab_pairs_at_r2"],
            "ab_pairs_found": dbg_counts["ab_pairs_found"],
            "stage1_swaps": dbg_counts["stage1_swaps"],
            "stage2_swaps": dbg_counts["stage2_swaps"],
            "pair_counts": {"/".join(k): v for k, v in dbg_counts["pair_counts"].items()},
            "swap_rule_mem_counts": {k: v for k, v in dbg_counts["swap_rule_mem_counts"].items()},
            "accepted_res": accepted_res,
        },
    }


def run_trials(args: argparse.Namespace) -> Dict[str, any]:
    resolved = SimpleNamespace(**vars(args))
    if resolved.sanity == "ideal":
        resolved.distance = 1.0
        resolved.attn = 2e-4
        resolved.cc_delay = 1e6
        resolved.eta_source = 1.0
        resolved.eta_dest = 1.0
        resolved.dqt_eta_source = 1.0
        resolved.dqt_eta_dest = 1.0
        resolved.swap_success = 1.0
        resolved.mem_coh_s = 1.0
        resolved.qt_eff = None
        resolved.fidelity = 0.5
    pt = set_strategy(resolved.strategy)
    dqt_prob = resolved.qt_eff if resolved.qt_eff is not None else resolved.dqt_eta_source * resolved.dqt_eta_dest
    orig_create = patch_generation(pt, resolved.eta_source, resolved.eta_dest, dqt_prob if pt == DQT else None)
    total_distance = 3 * resolved.distance
    start_time_ps, end_time_ps, setup_slack_s = compute_window(resolved, total_distance)
    deadline_ps = end_time_ps
    successes = 0
    times: List[int] = []
    debug_acc = {
        "entangled_total": 0,
        "swap_events": 0,
        "link_counts": defaultdict(int),
        "accepted_res": defaultdict(int),
        "swap_rules_created": defaultdict(int),
        "ab_pairs_at_r2": 0,
        "ab_pairs_found": 0,
        "stage1_swaps": 0,
        "stage2_swaps": 0,
        "pair_counts": defaultdict(int),
    }
    try:
        for i in range(resolved.num_trials):
            res = run_trial(i, resolved, pt, start_time_ps, end_time_ps)
            if res["success"]:
                successes += 1
                times.append(res["t_success"])  # type: ignore
            if resolved.debug:
                dbg = res["dbg"]  # type: ignore
                debug_acc["entangled_total"] += dbg["entangled_total"]
                debug_acc["swap_events"] += dbg["swap_events"]
                for lk, cnt in dbg["link_counts"].items():
                    debug_acc["link_counts"][lk] += cnt
                for node, cnt in dbg["accepted_res"].items():
                    debug_acc["accepted_res"][node] += cnt
                for node, cnt in dbg.get("swap_rules_created", {}).items():
                    debug_acc["swap_rules_created"][node] += cnt
                debug_acc["ab_pairs_at_r2"] += dbg.get("ab_pairs_at_r2", 0)
                debug_acc["ab_pairs_found"] += dbg.get("ab_pairs_found", 0)
                debug_acc["stage1_swaps"] += dbg.get("stage1_swaps", 0)
                debug_acc["stage2_swaps"] += dbg.get("stage2_swaps", 0)
                for pair, cnt in dbg.get("pair_counts", {}).items():
                    debug_acc["pair_counts"][pair] += cnt
                debug_acc["swap_rule_mem_counts"] = dbg.get("swap_rule_mem_counts", {})
                print(json.dumps({
                    "trial": i,
                    "success": res["success"],
                    "t_success": res["t_success"],
                    "entangled_total": dbg["entangled_total"],
                    "link_counts": dbg["link_counts"],
                    "swap_events": dbg["swap_events"],
                    "ab_pairs_found": dbg.get("ab_pairs_found", 0),
                    "stage1_swaps": dbg.get("stage1_swaps", 0),
                    "stage2_swaps": dbg.get("stage2_swaps", 0),
                    "pair_counts": dbg.get("pair_counts", {}),
                    "swap_rules_created": dbg.get("swap_rules_created", {}),
                    "ab_pairs_at_r2": dbg.get("ab_pairs_at_r2", 0),
                    "swap_rule_mem_counts": dbg.get("swap_rule_mem_counts", {}),
                    "accepted_res": dbg["accepted_res"],
                }))
    finally:
        restore_generation(orig_create)

    availability = successes / resolved.num_trials if resolved.num_trials > 0 else 0.0
    mean_t = float(np.mean(times)) if times else None
    result = {
        "arch": resolved.arch,
        "strategy": resolved.strategy,
        "distance_per_link": resolved.distance,
        "total_distance": total_distance,
        "deadline_ps": deadline_ps,
        "deadline_s": ps_to_sec(deadline_ps),
        "deadline_mode": resolved.deadline_mode,
        "deadline_factor": resolved.deadline_factor,
        "fiber_v": resolved.fiber_v,
        "setup_slack_s": setup_slack_s,
        "start_time_ps": start_time_ps,
        "start_time_s": ps_to_sec(start_time_ps),
        "num_trials": resolved.num_trials,
        "satisfied": successes,
        "availability_req": availability,
        "mean_t_success": mean_t,
        "params": {
            "eta_source": resolved.eta_source,
            "eta_dest": resolved.eta_dest,
            "dqt_eta_source": resolved.dqt_eta_source,
            "dqt_eta_dest": resolved.dqt_eta_dest,
            "qt_eff": resolved.qt_eff,
            "swap_success": resolved.swap_success,
            "mem_coh_s": resolved.mem_coh_s,
            "attn": resolved.attn,
            "cc_delay": resolved.cc_delay,
            "sanity": resolved.sanity,
        },
    }
    if resolved.debug:
        result["debug_summary"] = {
            "entangled_total": debug_acc["entangled_total"],
            "swap_events": debug_acc["swap_events"],
            "link_counts": dict(debug_acc["link_counts"]),
            "accepted_res": dict(debug_acc["accepted_res"]),
            "swap_rules_created": dict(debug_acc["swap_rules_created"]),
            "ab_pairs_at_r2": debug_acc["ab_pairs_at_r2"],
            "ab_pairs_found": debug_acc["ab_pairs_found"],
            "stage1_swaps": debug_acc["stage1_swaps"],
            "stage2_swaps": debug_acc["stage2_swaps"],
            "pair_counts": dict(debug_acc["pair_counts"]),
            "swap_rule_mem_counts": debug_acc.get("swap_rule_mem_counts", {}),
        }
    return result


def emit(result: Dict[str, any], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(result, indent=2)
    headers = [
        "arch",
        "strategy",
        "distance_per_link",
        "deadline_ps",
        "deadline_s",
        "setup_slack_s",
        "start_time_ps",
        "start_time_s",
        "num_trials",
        "satisfied",
        "availability_req",
        "mean_t_success",
    ]
    if fmt == "csv":
        values = [str(result.get(h, "")) for h in headers]
        return ",".join(headers) + "\n" + ",".join(values)
    row = [
        result.get("arch"),
        result.get("strategy"),
        f"{result.get('distance_per_link')}",
        f"{result.get('deadline_ps')}",
        f"{result.get('deadline_s'):.6f}",
        f"{result.get('setup_slack_s'):.6f}",
        f"{result.get('start_time_ps')}",
        f"{result.get('start_time_s'):.6f}",
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
