"""Calibrate deadline_factor to avoid saturation for network availability (line4)."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable, List, Tuple

import numpy as np

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


def build_args(base, arch: str, strategy: str, distance: float, factor: float, seed: int) -> Tuple[SimpleNamespace, float, float]:
    total_distance = 3 * distance
    slack = max(base.min_start_delay_s, base.setup_factor * total_distance / base.fiber_v)
    deadline_s = None
    if base.deadline_mode == "scaled":
        deadline_s = factor * total_distance / base.fiber_v
    else:
        deadline_s = base.deadline_s
    if deadline_s <= slack:
        raise ValueError(f"deadline_s {deadline_s} too small vs slack {slack} (factor={factor})")

    eta_source = base.eta_source
    eta_dest = base.eta_dest
    dqt_eta_source = base.dqt_eta_source
    dqt_eta_dest = base.dqt_eta_dest
    if arch == "optical":
        eta_source = eta_dest = 1.0
        dqt_eta_source = dqt_eta_dest = 1.0

    ns = SimpleNamespace(
        strategy=strategy,
        arch=arch,
        distance=distance,
        deadline_mode=base.deadline_mode,
        deadline_ps=None,
        deadline_s=deadline_s,
        deadline_factor=factor,
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
    return ns, deadline_s, slack


def write_csv(path: Path, headers: List[str], rows: Iterable[Tuple]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Calibrate deadline_factor to avoid availability saturation.")
    p.add_argument("--strategies", default="BK,EQT,DQT")
    p.add_argument("--archs", default="optical,hybrid")
    p.add_argument("--distance", type=float, default=1000.0, help="Per-link distance (m).")
    p.add_argument("--factors", default="50,100,200,500,700,1000,1500,2000,5000")
    p.add_argument("--seeds", default="0,1,2")
    p.add_argument("--num-trials", type=int, default=10)
    p.add_argument("--deadline-mode", choices=["absolute", "scaled"], default="scaled")
    p.add_argument("--deadline-s", type=float, default=0.1)
    p.add_argument("--deadline-factor", type=float, default=2000.0, help="Unused when factors list provided; kept for compatibility.")
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
    p.add_argument("--fidelity", type=float, default=0.5)
    p.add_argument("--sanity", choices=["off", "ideal"], default="off")
    p.add_argument("--target-low", type=float, default=0.2)
    p.add_argument("--target-high", type=float, default=0.8)
    p.add_argument("--recommend-common-factor", action="store_true", help="If set, compute a single factor per arch that minimizes saturation across strategies.")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_deadline_calibrate"))
    return p.parse_args()


def main():
    args = parse_args()
    strategies = parse_list(args.strategies, str)
    archs = parse_list(args.archs, str)
    factors = parse_list(args.factors, float)
    seeds = parse_list(args.seeds, int)

    raw_rows = []
    agg_map = defaultdict(list)

    for arch in archs:
        for strategy in strategies:
            for factor in factors:
                for seed in seeds:
                    try:
                        ns, deadline_s, slack = build_args(args, arch, strategy, args.distance, factor, seed)
                    except ValueError as e:
                        print(f"Skip factor {factor} arch={arch} strat={strategy}: {e}")
                        continue
                    res = run_trials(ns)
                    raw_rows.append(
                        (
                            arch,
                            strategy,
                            args.distance,
                            factor,
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
                    agg_map[(arch, strategy, factor)].append(res["availability_req"])

    raw_headers = [
        "arch",
        "strategy",
        "distance",
        "factor",
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
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "deadline_cal_raw.csv"
    write_csv(raw_path, raw_headers, raw_rows)

    agg_headers = [
        "arch",
        "strategy",
        "distance",
        "factor",
        "runs",
        "availability_mean",
        "availability_std",
        "availability_ci95",
        "deadline_s",
        "deadline_ps",
        "setup_slack_s",
    ]
    agg_rows = []
    by_arch_strategy = defaultdict(list)
    for (arch, strategy, factor), vals in agg_map.items():
        n = len(vals)
        mean = float(np.mean(vals)) if vals else 0.0
        std = float(np.std(vals, ddof=0)) if vals else 0.0
        ref_deadline_s = None
        ref_deadline_ps = None
        ref_slack = None
        for row in raw_rows:
            if row[0] == arch and row[1] == strategy and row[2] == args.distance and row[3] == factor:
                ref_deadline_s = row[9]
                ref_deadline_ps = row[10]
                ref_slack = row[11]
                break
        agg_rows.append(
            (
                arch,
                strategy,
                args.distance,
                factor,
                n,
                mean,
                std,
                ci95(std, n),
                ref_deadline_s,
                ref_deadline_ps,
                ref_slack,
            )
        )
        by_arch_strategy[(arch, strategy)].append((factor, mean))

    agg_path = out_dir / "deadline_cal_agg.csv"
    write_csv(agg_path, agg_headers, agg_rows)

    # recommendation
    rec_lines = []
    for key, vals in by_arch_strategy.items():
        arch, strategy = key
        vals.sort(key=lambda x: x[0])
        in_band = [v for v in vals if args.target_low <= v[1] <= args.target_high]
        if in_band:
            rec = in_band[0]
        else:
            rec = min(vals, key=lambda v: abs(v[1] - 0.5))
        rec_lines.append((arch, strategy, rec[0], rec[1]))
    rec_path = out_dir / "deadline_cal_recommendations.csv"
    write_csv(rec_path, ["arch", "strategy", "factor", "availability_mean"], rec_lines)

    common_lines = []
    if args.recommend_common_factor:
        # choose a single factor per arch minimizing saturation across strategies
        by_arch = defaultdict(list)
        for arch, strategy in [(k[0], k[1]) for k in by_arch_strategy.keys()]:
            if strategy not in by_arch[arch]:
                by_arch[arch].append(strategy)
        factors = sorted({row[3] for row in agg_rows})
        for arch in set([k[0] for k in by_arch_strategy.keys()]):
            best = None
            for f in factors:
                avails = []
                for strat in by_arch[arch]:
                    key = (arch, strat)
                    vals = [v for v in by_arch_strategy[key] if v[0] == f]
                    if not vals:
                        break
                    avails.append(vals[0][1])
                else:
                    penalty = 0.0
                    for a in avails:
                        if a < args.target_low or a > args.target_high:
                            penalty += 10.0
                        penalty += abs(a - 0.5)
                    score = penalty
                    if best is None or score < best[0]:
                        best = (score, f, avails)
            if best is not None:
                common_lines.append((arch, best[1], *best[2]))
        common_path = out_dir / "deadline_cal_common_factors.csv"
        headers = ["arch", "factor"] + [f"avail_{s}" for s in sorted(set([k[1] for k in by_arch_strategy.keys()]))]
        write_csv(common_path, headers, common_lines)

    print(f"Wrote raw to {raw_path}")
    print(f"Wrote agg to {agg_path}")
    print(f"Wrote recommendations to {rec_path}")
    for line in rec_lines:
        print(f"Recommend factor {line[2]} for arch={line[0]} strategy={line[1]} (mean={line[3]:.3f})")
    if args.recommend_common_factor and common_lines:
        print(f"Wrote common factors to {common_path}")
        for line in common_lines:
            arch = line[0]
            factor = line[1]
            avs = line[2:]
            print(f"Common factor {factor} for arch={arch} avails={avs}")


if __name__ == "__main__":
    main()
