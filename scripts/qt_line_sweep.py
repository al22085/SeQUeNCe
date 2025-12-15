"""Distance/seed sweep runner for BK/DQT/EQT availability (fixed_attempts)."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Iterable, List

# Ensure repo root on sys.path when executed directly
ROOT_DIR = Path(__file__).resolve().parents[1]
import sys

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.qt_line_availability import run_experiment  # noqa: E402


def _parse_floats(csv_str: str) -> List[float]:
    return [float(x) for x in csv_str.split(",") if x.strip()]


def _parse_ints(csv_str: str) -> List[int]:
    return [int(x) for x in csv_str.split(",") if x.strip()]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep BK/DQT/EQT availability over distances and seeds.")
    parser.add_argument("--strategies", type=str, default="BK,DQT,EQT", help="Comma list of strategies.")
    parser.add_argument("--distances", type=str, required=True, help="Comma list of distances (meters).")
    parser.add_argument("--seeds", type=str, required=True, help="Comma list of seeds.")
    parser.add_argument("--attempts", type=int, default=200, help="Attempts per seed (fixed_attempts mode).")
    parser.add_argument("--eta-source", type=float, default=0.8, help="EQT: source efficiency.")
    parser.add_argument("--eta-dest", type=float, default=0.8, help="EQT: dest efficiency.")
    parser.add_argument("--qt-eff", type=float, default=None, help="DQT: legacy success probability (overridden by dqt-eta-*).")
    parser.add_argument("--dqt-eta-source", type=float, default=1.0, help="DQT: source efficiency (default 1.0)")
    parser.add_argument("--dqt-eta-dest", type=float, default=0.7, help="DQT: dest efficiency (default 0.7 => matches prior 0.7 qt_eff)")
    parser.add_argument("--stop-time", type=float, default=5e12, help="Timeline stop_time safety cap.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory to write raw/aggregated CSV.")
    return parser.parse_args()


def aggregate_availability(values: Iterable[float]) -> dict:
    vals = list(values)
    n = len(vals)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "ci95": 0.0, "n": 0}
    m = mean(vals)
    std = pstdev(vals) if n > 1 else 0.0
    ci95 = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
    return {"mean": m, "std": std, "ci95": ci95, "n": n}


def write_raw(out_path: Path, rows: list[dict]) -> None:
    fields = [
        "strategy",
        "distance",
        "seed",
        "eta_source",
        "eta_dest",
        "num_attempts",
        "num_entangled",
        "availability",
        "mode",
        "stop_time",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in fields})


def write_agg(out_path: Path, rows: list[dict]) -> None:
    fields = [
        "strategy",
        "distance",
        "attempts_target",
        "n_seeds",
        "availability_mean",
        "availability_std",
        "availability_ci95",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
                writer.writerow(r)


def main() -> None:
    args = parse_args()
    strategies = [s.strip() for s in args.strategies.split(",") if s.strip()]
    distances = _parse_floats(args.distances)
    seeds = _parse_ints(args.seeds)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    raw_rows: list[dict] = []

    for strategy in strategies:
        for dist in distances:
            for seed in seeds:
                result = run_experiment(
                    strategy=strategy,
                    num_trials=args.attempts,
                    seed=seed,
                    eta_source=args.eta_source,
                    eta_dest=args.eta_dest,
                    qt_eff=args.qt_eff,
                    distance=dist,
                    mode="fixed_attempts",
                    stop_time=args.stop_time,
                    dqt_eta_source=args.dqt_eta_source,
                    dqt_eta_dest=args.dqt_eta_dest,
                )
                result["seed"] = seed
                result["num_attempts"] = args.attempts  # target attempts per seed
                raw_rows.append(result)

    raw_path = args.out_dir / "qt_line_raw.csv"
    write_raw(raw_path, raw_rows)

    agg_rows = []
    for strategy in strategies:
        for dist in distances:
            vals = [r["availability"] for r in raw_rows if r["strategy"] == strategy and r["distance"] == dist]
            stats = aggregate_availability(vals)
            agg_rows.append(
                {
                    "strategy": strategy,
                    "distance": dist,
                    "attempts_target": args.attempts,
                    "n_seeds": stats["n"],
                    "availability_mean": stats["mean"],
                    "availability_std": stats["std"],
                    "availability_ci95": stats["ci95"],
                }
            )

    agg_path = args.out_dir / "qt_line_agg.csv"
    write_agg(agg_path, agg_rows)

    # terse summary
    print("Raw CSV:", raw_path)
    print("Agg CSV:", agg_path)
    for row in agg_rows[:5]:
        print(
            f"{row['strategy']} dist={row['distance']:.0f} n={row['n_seeds']} "
            f"avail={row['availability_mean']:.3f}±{row['availability_std']:.3f}"
        )


if __name__ == "__main__":
    main()
