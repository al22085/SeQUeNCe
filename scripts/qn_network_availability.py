"""Network-level availability benchmark on a 4-node line (A-R1-R2-B)."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np


@dataclass
class ArchDefaults:
    strategy: str
    base_link_success: float
    swap_success: float
    mem_coh_end: float
    mem_coh_rep: float
    eta_source: float
    eta_dest: float
    dqt_eta_source: float
    dqt_eta_dest: float


ARCH_PROFILES = {
    "optical": ArchDefaults(
        strategy="BK",
        base_link_success=0.35,
        swap_success=0.5,
        mem_coh_end=1e6,
        mem_coh_rep=1e6,
        eta_source=1.0,
        eta_dest=1.0,
        dqt_eta_source=1.0,
        dqt_eta_dest=1.0,
    ),
    "hybrid": ArchDefaults(
        strategy="EQT",
        base_link_success=0.5,
        swap_success=0.8,
        mem_coh_end=5e5,
        mem_coh_rep=5e5,
        eta_source=0.8,
        eta_dest=0.8,
        dqt_eta_source=0.8,
        dqt_eta_dest=0.8,
    ),
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Request-level availability on A-R1-R2-B line with swapping.")
    p.add_argument("--arch", choices=list(ARCH_PROFILES.keys()), default="optical", help="Preset architecture.")
    p.add_argument("--strategy", choices=["BK", "DQT", "EQT"], help="EG strategy (defaults by arch).")
    p.add_argument("--distance", type=float, default=1e3, help="Per-link distance (m).")
    p.add_argument("--deadline", type=float, default=50.0, help="Deadline in time units; attempt_time=1 by default.")
    p.add_argument("--attempt-time", type=float, default=1.0, help="Time consumed per attempt.")
    p.add_argument("--num-trials", type=int, default=100, help="Number of service requests.")
    p.add_argument("--seed", type=int, default=0, help="Base RNG seed.")
    p.add_argument("--eta-source", type=float, default=None, help="EQT: source transducer efficiency.")
    p.add_argument("--eta-dest", type=float, default=None, help="EQT: dest transducer efficiency.")
    p.add_argument("--dqt-eta-source", type=float, default=None, help="DQT: source efficiency.")
    p.add_argument("--dqt-eta-dest", type=float, default=None, help="DQT: dest efficiency.")
    p.add_argument("--qt-eff", type=float, default=None, help="Legacy DQT success prob (overrides dqt etas).")
    p.add_argument("--swap-success", type=float, default=None, help="Swap/BSM success probability.")
    p.add_argument("--base-link-success", type=float, default=None, help="Per-link success before eta/scaling.")
    p.add_argument("--mem-coh-end", type=float, default=None, help="Memory coherence time (ends).")
    p.add_argument("--mem-coh-rep", type=float, default=None, help="Memory coherence time (repeaters).")
    p.add_argument("--format", choices=["md", "json", "csv"], default="md", help="Output format.")
    p.add_argument("--out", type=Path, default=None, help="Optional output file path.")
    return p.parse_args()


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def compute_per_attempt_success(
    strategy: str,
    base_link_success: float,
    swap_success: float,
    eta_source: float,
    eta_dest: float,
    dqt_eta_source: float,
    dqt_eta_dest: float,
    distance: float,
    mem_coh_end: float,
    mem_coh_rep: float,
    attempt_time: float,
) -> float:
    # crude distance scaling: exponential loss
    loss_factor = math.exp(-distance / 2e4)
    link_prob = base_link_success * loss_factor
    if strategy == "EQT":
        link_prob *= eta_source * eta_dest
    elif strategy == "DQT":
        link_prob *= dqt_eta_source * dqt_eta_dest
    link_prob = _clamp01(link_prob)

    # three elementary links, two swaps
    p_links = link_prob ** 3
    p_swaps = swap_success ** 2

    # decoherence penalty over attempt time
    coh_factor = math.exp(-attempt_time / mem_coh_end) * math.exp(-attempt_time / mem_coh_rep)

    return _clamp01(p_links * p_swaps * coh_factor)


def run_trials(args: argparse.Namespace) -> Dict[str, Any]:
    defaults = ARCH_PROFILES[args.arch]
    strategy = args.strategy or defaults.strategy
    base_link_success = defaults.base_link_success if args.base_link_success is None else args.base_link_success
    swap_success = defaults.swap_success if args.swap_success is None else args.swap_success
    eta_source = defaults.eta_source if args.eta_source is None else args.eta_source
    eta_dest = defaults.eta_dest if args.eta_dest is None else args.eta_dest
    dqt_eta_source = defaults.dqt_eta_source if args.dqt_eta_source is None else args.dqt_eta_source
    dqt_eta_dest = defaults.dqt_eta_dest if args.dqt_eta_dest is None else args.dqt_eta_dest
    if args.qt_eff is not None:
        dqt_eta_source = 1.0
        dqt_eta_dest = args.qt_eff

    mem_coh_end = defaults.mem_coh_end if args.mem_coh_end is None else args.mem_coh_end
    mem_coh_rep = defaults.mem_coh_rep if args.mem_coh_rep is None else args.mem_coh_rep

    max_attempts = max(1, int(args.deadline / args.attempt_time))
    per_attempt_success = compute_per_attempt_success(
        strategy,
        base_link_success,
        swap_success,
        eta_source,
        eta_dest,
        dqt_eta_source,
        dqt_eta_dest,
        args.distance,
        mem_coh_end,
        mem_coh_rep,
        args.attempt_time,
    )

    rng = np.random.default_rng(args.seed)
    satisfied = 0
    times_success: List[float] = []

    for i in range(args.num_trials):
        rng_trial = rng
        for att in range(max_attempts):
            if rng_trial.random() < per_attempt_success:
                satisfied += 1
                times_success.append((att + 1) * args.attempt_time)
                break

    availability_req = satisfied / args.num_trials if args.num_trials > 0 else 0.0
    mean_t_success = float(np.mean(times_success)) if times_success else None

    return {
        "arch": args.arch,
        "strategy": strategy,
        "distance_per_link": args.distance,
        "deadline": args.deadline,
        "num_trials": args.num_trials,
        "satisfied": satisfied,
        "availability_req": availability_req,
        "mean_t_success": mean_t_success,
        "attempt_time": args.attempt_time,
        "max_attempts": max_attempts,
        "per_attempt_success": per_attempt_success,
        "params": {
            "base_link_success": base_link_success,
            "swap_success": swap_success,
            "eta_source": eta_source,
            "eta_dest": eta_dest,
            "dqt_eta_source": dqt_eta_source,
            "dqt_eta_dest": dqt_eta_dest,
            "mem_coh_end": mem_coh_end,
            "mem_coh_rep": mem_coh_rep,
        },
    }


def emit(result: Dict[str, Any], fmt: str) -> str:
    if fmt == "json":
        return json.dumps(result, indent=2)
    if fmt == "csv":
        headers = [
            "arch",
            "strategy",
            "distance_per_link",
            "deadline",
            "num_trials",
            "satisfied",
            "availability_req",
            "mean_t_success",
            "per_attempt_success",
        ]
        values = [str(result.get(h, "")) for h in headers]
        return ",".join(headers) + "\n" + ",".join(values)
    # md
    headers = ["arch", "strategy", "distance_per_link", "deadline", "num_trials", "satisfied", "availability_req", "mean_t_success"]
    row = [result.get("arch"), result.get("strategy"), f"{result.get('distance_per_link')}", f"{result.get('deadline')}", str(result.get("num_trials")), str(result.get("satisfied")), f"{result.get('availability_req'):.3f}", "N/A" if result.get("mean_t_success") is None else f"{result.get('mean_t_success'):.2f}"]
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
