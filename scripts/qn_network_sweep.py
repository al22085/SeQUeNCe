"""Sweep network availability over distance/strategy/arch using qn_network_availability_sequence."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, List, Tuple

import math
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_network_availability_sequence import run_trials


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def ci95(std: float, n: int) -> float:
    if n <= 0:
        return 0.0
    return 1.96 * std / math.sqrt(n)


def build_args(base, arch: str, strategy: str, distance: float, seed: int) -> SimpleNamespace:
    eta_source = base.eta_source
    eta_dest = base.eta_dest
    dqt_eta_source = base.dqt_eta_source
    dqt_eta_dest = base.dqt_eta_dest
    if arch == "optical":
        eta_source = eta_dest = 1.0
        dqt_eta_source = dqt_eta_dest = 1.0
    elif arch == "hybrid":
        eta_source = base.eta_source
        eta_dest = base.eta_dest
        dqt_eta_source = base.dqt_eta_source
        dqt_eta_dest = base.dqt_eta_dest

    return SimpleNamespace(
        strategy=strategy,
        arch=arch,
        distance=distance,
        deadline_mode=base.deadline_mode,
        deadline_ps=None,
        deadline_s=base.deadline_s,
        deadline_factor=base.deadline_factor,
        fiber_v=base.fiber_v,
        setup_factor=base.setup_factor,
        min_start_delay_s=base.min_start_delay_s,
        num_trials=base.num_trials,
        seed=seed,
        fidelity=base.fidelity,
        eta_source=eta_source,
        eta_dest=eta_dest,
        dqt_eta_source=dqt_eta_source,
        dqt_eta_dest=dqt_eta_dest,
        qt_eff=base.qt_eff,
        swap_success=base.swap_success,
        mem_coh_s=base.mem_coh_s,
        attn=base.attn,
        cc_delay=base.cc_delay,
        sanity=base.sanity,
        format="json",
        out=None,
        debug=False,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sweep network availability over distance/strategy/arch.")
    p.add_argument("--strategies", default="BK,EQT,DQT", help="Comma list of strategies.")
    p.add_argument("--archs", default="optical,hybrid", help="Comma list of arch presets.")
    p.add_argument("--distances", default="100,500,1000", help="Comma list of per-link distances (m).")
    p.add_argument("--seeds", default="0,1,2", help="Comma list of seeds.")
    p.add_argument("--num-trials", type=int, default=10, help="Trials per (arch,strategy,distance,seed).")
    p.add_argument("--deadline-mode", choices=["absolute", "scaled"], default="scaled")
    p.add_argument("--deadline-s", type=float, default=0.1)
    p.add_argument("--deadline-factor", type=float, default=2000.0)
    p.add_argument("--fiber-v", type=float, default=2e8)
    p.add_argument("--setup-factor", type=float, default=500.0)
    p.add_argument("--min-start-delay-s", type=float, default=0.01)
    p.add_argument("--eta-source", type=float, default=0.8)
    p.add_argument("--eta-dest", type=float, default=0.8)
    p.add_argument("--dqt-eta-source", type=float, default=0.8)
    p.add_argument("--dqt-eta-dest", type=float, default=0.8)
    p.add_argument("--qt-eff", type=float, default=None)
    p.add_argument("--swap-success", type=float, default=1.0)
    p.add_argument("--mem-coh-s", type=float, default=1.0)
    p.add_argument("--attn", type=float, default=2e-4)
    p.add_argument("--cc-delay", type=float, default=1e6)
    p.add_argument("--fidelity", type=float, default=0.9)
    p.add_argument("--sanity", choices=["off", "ideal"], default="off")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_network_sweep"))
    return p.parse_args()


def write_csv(path: Path, headers: List[str], rows: Iterable[Tuple]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def main():
    args = parse_args()
    strategies = parse_list(args.strategies, str)
    archs = parse_list(args.archs, str)
    distances = parse_list(args.distances, float)
    seeds = parse_list(args.seeds, int)

    raw_rows = []
    agg_map = defaultdict(list)

    for arch in archs:
        for strategy in strategies:
            for dist in distances:
                for seed in seeds:
                    ns = build_args(args, arch, strategy, dist, seed)
                    res = run_trials(ns)
                    raw_rows.append(
                        (
                            arch,
                            strategy,
                            dist,
                            seed,
                            res["num_trials"],
                            res["satisfied"],
                            res["availability_req"],
                            res["mean_t_success"],
                            res["deadline_s"],
                            res["deadline_ps"],
                            res["setup_slack_s"],
                        )
                    )
                    agg_key = (arch, strategy, dist)
                    agg_map[agg_key].append(res)

    raw_headers = [
        "arch",
        "strategy",
        "distance",
        "seed",
        "num_trials",
        "satisfied",
        "availability_req",
        "mean_t_success",
        "deadline_s",
        "deadline_ps",
        "setup_slack_s",
    ]
    out_dir = args.out_dir
    raw_path = out_dir / "qn_network_raw.csv"
    write_csv(raw_path, raw_headers, raw_rows)

    agg_headers = [
        "arch",
        "strategy",
        "distance",
        "runs",
        "total_trials",
        "total_satisfied",
        "availability_mean",
        "availability_std",
        "availability_ci95",
        "deadline_s",
        "deadline_ps",
        "setup_slack_s",
    ]
    agg_rows = []
    for key, res_list in agg_map.items():
        arch, strategy, dist = key
        n = len(res_list)
        avail_list = [r["availability_req"] for r in res_list]
        import numpy as np

        mean = float(np.mean(avail_list)) if avail_list else 0.0
        std = float(np.std(avail_list, ddof=0)) if avail_list else 0.0
        total_trials = sum(r["num_trials"] for r in res_list)
        total_satisfied = sum(r["satisfied"] for r in res_list)
        ref = res_list[0]
        agg_rows.append(
            (
                arch,
                strategy,
                dist,
                n,
                total_trials,
                total_satisfied,
                mean,
                std,
                ci95(std, n),
                ref["deadline_s"],
                ref["deadline_ps"],
                ref["setup_slack_s"],
            )
        )

    agg_path = out_dir / "qn_network_agg.csv"
    write_csv(agg_path, agg_headers, agg_rows)

    print(f"Wrote raw to {raw_path}")
    print(f"Wrote agg to {agg_path}")


if __name__ == "__main__":
    main()
