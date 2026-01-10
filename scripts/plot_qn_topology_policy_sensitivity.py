"""Plot topology+policy upgrade-k curves and export pooled summaries."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Plot topology/policy upgrade-k sensitivity results.")
    p.add_argument("--root-dir", type=Path, default=Path("out/topology_policy_upgrade_curves"))
    p.add_argument("--summary-csv", type=Path, default=None)
    p.add_argument("--curve-points-glob", type=str, default="**/curve_points.csv")
    p.add_argument("--out-dir", type=Path, default=None)
    return p.parse_args()


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def classify_curve(c1: float, c2: float) -> str:
    if max(abs(c1), abs(c2)) < 0.01:
        return "linear-ish"
    return "threshold"


def main():
    args = parse_args()
    summary_csv = args.summary_csv or (args.root_dir / "summary_upgrade_curves.csv")
    if not summary_csv.exists():
        raise SystemExit(f"Missing summary CSV: {summary_csv}")
    out_dir = args.out_dir or (args.root_dir / "plots")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = load_rows(summary_csv)
    topologies = sorted({r["topology_id"] for r in rows})
    policies = sorted({r["policy"] for r in rows})
    metrics = sorted({r["metric"] for r in rows})

    # load curve points (median + worst_case are included as pair labels)
    curve_points = []
    for path in args.root_dir.glob(args.curve_points_glob):
        curve_points.extend(load_rows(path))

    # per-topology plots (policies overlaid, median)
    for topo in topologies:
        for metric in metrics:
            plt.figure(figsize=(6, 4))
            for policy in policies:
                pts = [
                    p
                    for p in curve_points
                    if p["pair"] == metric
                    and p.get("topology_id", topo) == topo
                    and p.get("upgrade_policy", policy) == policy
                ]
                if not pts:
                    continue
                pts_sorted = sorted(pts, key=lambda x: float(x["upgrade_k"]))
                xs = [float(p["upgraded_fraction"]) for p in pts_sorted]
                ys = [float(p["ratio_vs_bk0"]) for p in pts_sorted]
                plt.plot(xs, ys, marker="o", label=policy)
            plt.xlabel("upgraded_fraction (k/Kmax)")
            plt.ylabel("EQT/BK0 ratio")
            plt.title(f"{topo} ({metric})")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(out_dir / f"{topo}_policy_ratio_{metric}.png")
            plt.close()

    # per-policy plots (topologies overlaid, median)
    for policy in policies:
        for metric in metrics:
            plt.figure(figsize=(6, 4))
            for topo in topologies:
                pts = [
                    p
                    for p in curve_points
                    if p["pair"] == metric
                    and p.get("topology_id", topo) == topo
                    and p.get("upgrade_policy", policy) == policy
                ]
                if not pts:
                    continue
                pts_sorted = sorted(pts, key=lambda x: float(x["upgrade_k"]))
                xs = [float(p["upgraded_fraction"]) for p in pts_sorted]
                ys = [float(p["ratio_vs_bk0"]) for p in pts_sorted]
                plt.plot(xs, ys, marker="o", label=topo)
            plt.xlabel("upgraded_fraction (k/Kmax)")
            plt.ylabel("EQT/BK0 ratio")
            plt.title(f"{policy} ({metric})")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(out_dir / f"{policy}_topology_ratio_{metric}.png")
            plt.close()

    # pooled summary across topologies
    pooled_rows = []
    for policy in policies:
        for metric in metrics:
            ratios_by_frac: Dict[float, List[float]] = {}
            for p in curve_points:
                if p["pair"] != metric:
                    continue
                if p.get("upgrade_policy", policy) != policy:
                    continue
                frac = float(p["upgraded_fraction"])
                ratios_by_frac.setdefault(frac, []).append(float(p["ratio_vs_bk0"]))
            for frac in sorted(ratios_by_frac.keys()):
                vals = ratios_by_frac[frac]
                pooled_rows.append(
                    {
                        "policy": policy,
                        "metric": metric,
                        "upgraded_fraction": frac,
                        "ratio_median": float(np.median(vals)),
                        "ratio_worst": float(np.min(vals)),
                        "ratio_max": float(np.max(vals)),
                    }
                )
    pooled_path = out_dir / "policy_topology_pooled_ratios.csv"
    with pooled_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["policy", "metric", "upgraded_fraction", "ratio_median", "ratio_worst", "ratio_max"],
        )
        writer.writeheader()
        writer.writerows(pooled_rows)

    # curvature summary table
    curvature_rows = []
    for row in rows:
        curvature_val = float(row.get("curvature", 0.0) or 0.0)
        curvature_rows.append(
            {
                "topology_id": row["topology_id"],
                "policy": row["policy"],
                "metric": row["metric"],
                "ratio21": row.get("ratio_k21", row.get("ratio21", "")),
                "r2": row.get("r2", ""),
                "curvature": row.get("curvature", ""),
                "classification": row.get("classification", ""),
                "flat_then_jump": row.get("flat_then_jump", ""),
                "curve_shape": classify_curve(curvature_val, curvature_val),
            }
        )
    curvature_path = out_dir / "policy_topology_curvature_summary.csv"
    with curvature_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["topology_id", "policy", "metric", "ratio21", "r2", "curvature", "classification", "flat_then_jump", "curve_shape"],
        )
        writer.writeheader()
        writer.writerows(curvature_rows)

    print(f"Wrote {pooled_path}")
    print(f"Wrote {curvature_path}")


if __name__ == "__main__":
    main()
