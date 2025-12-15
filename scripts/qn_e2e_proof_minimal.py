"""Minimal A-B reservation proof using correct ps scheduling."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

import numpy as np

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
from sequence.topology.node import QuantumRouter, BSMNode
from sequence.app.request_app import RequestApp


def sec_to_ps(s: float) -> int:
    return int(round(s * 1e12))


def ps_to_sec(ps: int) -> float:
    return ps / 1e12


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Minimal reservation-based A-B entanglement proof.")
    p.add_argument("--strategy", choices=["BK", "DQT", "EQT"], default="BK")
    p.add_argument("--distance", type=float, default=1.0, help="Per-link distance (m).")
    p.add_argument("--deadline-s", type=float, default=0.1, help="Absolute deadline in seconds.")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--eta-source", type=float, default=1.0)
    p.add_argument("--eta-dest", type=float, default=1.0)
    p.add_argument("--dqt-eta-source", type=float, default=1.0)
    p.add_argument("--dqt-eta-dest", type=float, default=1.0)
    p.add_argument("--qt-eff", type=float, default=None)
    p.add_argument("--num-trials", type=int, default=20)
    p.add_argument("--setup-factor", type=float, default=5000.0)
    p.add_argument("--min-start-delay-s", type=float, default=0.01)
    p.add_argument("--fiber-v", type=float, default=2e8)
    p.add_argument("--attn", type=float, default=0.0)
    p.add_argument("--cc-delay", type=float, default=1e6)
    p.add_argument("--format", choices=["json", "md"], default="json")
    p.add_argument("--sanity", choices=["off", "ideal"], default="off", help="ideal forces distance=1m, eta=1.")
    return p.parse_args()


def set_strategy(proto: str) -> str:
    if proto == "BK":
        pt = BARRET_KOK
    elif proto == "DQT":
        pt = DQT
    else:
        pt = EQT
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


def build_link(tl: Timeline, distance: float, attn: float, cc_delay: float) -> tuple[QuantumRouter, QuantumRouter]:
    A = QuantumRouter("A", tl, memo_size=2)
    B = QuantumRouter("B", tl, memo_size=2)
    bsm = BSMNode("bsm", tl, [A.name, B.name])
    A.add_bsm_node(bsm.name, B.name)
    B.add_bsm_node(bsm.name, A.name)
    QuantumChannel("qc_A_bsm", tl, attenuation=attn, distance=distance).set_ends(A, bsm.name)
    QuantumChannel("qc_B_bsm", tl, attenuation=attn, distance=distance).set_ends(B, bsm.name)
    for src in (A, B, bsm):
        for dst in (A, B, bsm):
            if src.name == dst.name:
                continue
            ClassicalChannel(f"cc_{src.name}_{dst.name}", tl, 1e3, delay=cc_delay).set_ends(src, dst.name)
    A.network_manager.protocol_stack[0].update_forwarding_rule(B.name, B.name)
    B.network_manager.protocol_stack[0].update_forwarding_rule(A.name, A.name)
    return A, B


def compute_window(args: SimpleNamespace, total_distance: float) -> tuple[int, int, float]:
    deadline_s = args.deadline_s
    t_prop_s = total_distance / args.fiber_v
    setup_slack_s = max(args.min_start_delay_s, args.setup_factor * t_prop_s)
    start_time_ps = sec_to_ps(setup_slack_s)
    end_time_ps = sec_to_ps(deadline_s)
    if not isinstance(start_time_ps, int) or not isinstance(end_time_ps, int):
        raise ValueError("Reservation times must be int picoseconds.")
    if not (start_time_ps > 0 and end_time_ps > start_time_ps):
        raise ValueError(f"Invalid reservation window: now=0 start={start_time_ps} end={end_time_ps} slack_s={setup_slack_s} deadline_s={deadline_s}")
    return start_time_ps, end_time_ps, setup_slack_s


def run_trial(trial_idx: int, args: SimpleNamespace, pt: str, start_time_ps: int, end_time_ps: int) -> tuple[bool, Optional[int]]:
    tl = Timeline(stop_time=end_time_ps)
    seed = args.seed + trial_idx if args.seed is not None else None
    if seed is not None:
        np.random.seed(seed)

    A, B = build_link(tl, args.distance, args.attn, args.cc_delay)
    appA = RequestApp(A)
    appB = RequestApp(B)
    success_time = {"t": None}

    def wrap(app: RequestApp, remote: str):
        orig = app.get_memory

        def fn(info):
            orig(info)
            if info.state == "ENTANGLED" and info.remote_node == remote:
                if success_time["t"] is None:
                    success_time["t"] = tl.now()
                    tl.stop()
        return fn

    appA.get_memory = wrap(appA, B.name)  # type: ignore
    appB.get_memory = wrap(appB, A.name)  # type: ignore

    appA.start(B.name, start_t=start_time_ps, end_t=end_time_ps, memo_size=1, fidelity=0.9)
    tl.init()
    tl.run()
    return success_time["t"] is not None, success_time["t"]


def main() -> None:
    args = parse_args()
    resolved = SimpleNamespace(**vars(args))
    if resolved.sanity == "ideal":
        resolved.distance = 1.0
        resolved.attn = 0.0
        resolved.cc_delay = 1e6
        resolved.eta_source = 1.0
        resolved.eta_dest = 1.0
        resolved.dqt_eta_source = 1.0
        resolved.dqt_eta_dest = 1.0
        resolved.qt_eff = None
    pt = set_strategy(resolved.strategy)
    dqt_prob = resolved.qt_eff if resolved.qt_eff is not None else resolved.dqt_eta_source * resolved.dqt_eta_dest
    orig_create = patch_generation(pt, resolved.eta_source, resolved.eta_dest, dqt_prob if pt == DQT else None)

    start_time_ps, end_time_ps, setup_slack_s = compute_window(resolved, resolved.distance)

    successes = 0
    times = []
    try:
        for trial in range(resolved.num_trials):
            success, t_s = run_trial(trial, resolved, pt, start_time_ps, end_time_ps)
            if success:
                successes += 1
                times.append(t_s)
    finally:
        restore_generation(orig_create)

    availability = successes / resolved.num_trials if resolved.num_trials else 0.0
    result = {
        "strategy": resolved.strategy,
        "distance": resolved.distance,
        "num_trials": resolved.num_trials,
        "satisfied": successes,
        "availability_req": availability,
        "first_t_success_ps": None if not times else min([t for t in times if t is not None]),
        "deadline_ps": end_time_ps,
        "deadline_s": resolved.deadline_s,
        "setup_slack_s": setup_slack_s,
        "start_time_ps": start_time_ps,
        "start_time_s": ps_to_sec(start_time_ps),
    }

    if resolved.format == "md":
        print("| strategy | distance | num_trials | satisfied | availability_req | first_t_success_ps | deadline_s | setup_slack_s | start_time_ps |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        print(f"| {result['strategy']} | {result['distance']} | {result['num_trials']} | {result['satisfied']} | {result['availability_req']:.3f} | {result['first_t_success_ps']} | {result['deadline_s']:.3f} | {result['setup_slack_s']:.3f} | {result['start_time_ps']} |")
    else:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
