"""EQT eta sweep vs BK baseline for line topology (fixed_attempts)."""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List

import matplotlib.pyplot as plt

# Ensure repo root on sys.path
import sys

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.qt_line_availability import run_experiment  # noqa: E402


def _parse_floats(csv_str: str) -> List[float]:
    return [float(x) for x in csv_str.split(",") if x.strip()]


def _parse_ints(csv_str: str) -> List[int]:
    return [int(x) for x in csv_str.split(",") if x.strip()]


def aggregate(values: Iterable[float]) -> dict:
    vals = list(values)
    n = len(vals)
    if n == 0:
        return {"mean": 0.0, "std": 0.0, "ci95": 0.0, "n": 0}
    m = mean(vals)
    std = pstdev(vals) if n > 1 else 0.0
    ci95 = 1.96 * std / math.sqrt(n) if n > 1 else 0.0
    return {"mean": m, "std": std, "ci95": ci95, "n": n}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sweep EQT eta and compare to BK baseline.")
    parser.add_argument("--distance", type=float, default=1e3, help="Channel distance (m).")
    parser.add_argument("--etas", type=str, required=True, help="Comma list of eta values (0-1).")
    parser.add_argument("--seeds", type=str, required=True, help="Comma list of seeds.")
    parser.add_argument("--attempts", type=int, default=1000, help="Attempts per seed (fixed_attempts).")
    parser.add_argument("--stop-time", type=float, default=5e12, help="Timeline stop_time safety cap.")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for CSVs/plots.")
    return parser.parse_args()


def write_raw(path: Path, rows: List[Dict]) -> None:
    fields = [
        "strategy",
        "distance",
        "eta",
        "seed",
        "num_attempts",
        "num_entangled",
        "availability",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k) for k in fields})


def write_agg(path: Path, rows: List[Dict]) -> None:
    fields = [
        "strategy",
        "distance",
        "attempts_target",
        "eta",
        "n_seeds",
        "availability_mean",
        "availability_std",
        "availability_ci95",
        "predicted_from_bk",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def plot_eta_curve(agg_rows: List[Dict], bk_mean: float, distance: float, attempts: int, seeds_count: int, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    eqt_rows = sorted([r for r in agg_rows if r["strategy"] == "EQT"], key=lambda r: r["eta"])

    x = [r["eta"] for r in eqt_rows]
    y = [r["availability_mean"] for r in eqt_rows]
    ci = [r["availability_ci95"] for r in eqt_rows]
    pred = [bk_mean * (eta ** 2) for eta in x]

    fig, ax = plt.subplots(figsize=(7, 4))
    ax.errorbar(x, y, yerr=ci, fmt="o-", label="EQT measured", capsize=4, color="tab:green", markersize=5)
    ax.plot(x, pred, "o--", label="BK × eta^2 (theory)", color="tab:blue", markersize=4)
    ax.axhline(bk_mean, color="tab:gray", linestyle=":", label="BK mean")

    ax.set_xlabel("eta_source = eta_dest")
    ax.set_ylabel("Availability")
    ax.set_title(f"Distance={distance:.0f} m, attempts={attempts}, seeds={seeds_count}")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    for ext in ("png", "svg"):
        out_path = out_dir / f"qt_eta_sweep.{ext}"
        fig.savefig(out_path, dpi=200 if ext == "png" else None)
        print("Wrote", out_path)


def main() -> None:
    args = parse_args()
    etas = _parse_floats(args.etas)
    seeds = _parse_ints(args.seeds)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    raw_rows: List[Dict] = []

    # BK baseline (single per seed)
    bk_avails = []
    for seed in seeds:
        res = run_experiment(
            strategy="BK",
            num_trials=args.attempts,
            seed=seed,
            eta_source=1.0,
            eta_dest=1.0,
            qt_eff=1.0,
            distance=args.distance,
            mode="fixed_attempts",
            stop_time=args.stop_time,
        )
        bk_avails.append(res["availability"])
        raw_rows.append(
            {
                "strategy": "BK",
                "distance": args.distance,
                "eta": 1.0,
                "seed": seed,
                "num_attempts": args.attempts,
                "num_entangled": res["num_entangled"],
                "availability": res["availability"],
            }
        )
    bk_stats = aggregate(bk_avails)

    # EQT sweep
    for eta in etas:
        for seed in seeds:
            res = run_experiment(
                strategy="EQT",
                num_trials=args.attempts,
                seed=seed,
                eta_source=eta,
                eta_dest=eta,
                qt_eff=1.0,
                distance=args.distance,
                mode="fixed_attempts",
                stop_time=args.stop_time,
            )
            raw_rows.append(
                {
                    "strategy": "EQT",
                    "distance": args.distance,
                    "eta": eta,
                    "seed": seed,
                    "num_attempts": args.attempts,
                    "num_entangled": res["num_entangled"],
                    "availability": res["availability"],
                }
            )

    raw_path = out_dir / "qt_eta_raw.csv"
    write_raw(raw_path, raw_rows)

    agg_rows: List[Dict] = []
    agg_rows.append(
        {
            "strategy": "BK",
            "distance": args.distance,
            "attempts_target": args.attempts,
            "eta": 1.0,
            "n_seeds": bk_stats["n"],
            "availability_mean": bk_stats["mean"],
            "availability_std": bk_stats["std"],
            "availability_ci95": bk_stats["ci95"],
            "predicted_from_bk": bk_stats["mean"],
        }
    )

    for eta in etas:
        vals = [r["availability"] for r in raw_rows if r["strategy"] == "EQT" and r["eta"] == eta]
        stats = aggregate(vals)
        agg_rows.append(
            {
                "strategy": "EQT",
                "distance": args.distance,
                "attempts_target": args.attempts,
                "eta": eta,
                "n_seeds": stats["n"],
                "availability_mean": stats["mean"],
                "availability_std": stats["std"],
                "availability_ci95": stats["ci95"],
                "predicted_from_bk": bk_stats["mean"] * (eta ** 2),
            }
        )

    agg_path = out_dir / "qt_eta_agg.csv"
    write_agg(agg_path, agg_rows)

    plot_eta_curve(agg_rows, bk_mean=bk_stats["mean"], distance=args.distance, attempts=args.attempts, seeds_count=len(seeds), out_dir=out_dir / "figs")

    # summary
    print("BK mean availability:", f"{bk_stats['mean']:.3f} ± {bk_stats['std']:.3f} (n={bk_stats['n']})")
    for eta in etas[:5]:
        stats = [r for r in agg_rows if r["strategy"] == "EQT" and r["eta"] == eta][0]
        print(f"eta={eta:.2f} -> EQT {stats['availability_mean']:.3f}±{stats['availability_std']:.3f}, predicted {stats['predicted_from_bk']:.3f}")


if __name__ == "__main__":
    main()
