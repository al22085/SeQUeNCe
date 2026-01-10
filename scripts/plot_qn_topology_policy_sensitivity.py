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
    p.add_argument("--out-dir", type=Path, default=None)
    return p.parse_args()


def load_rows(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def ratios_from_row(row: Dict[str, str]) -> Dict[int, float]:
    ratios = {}
    for key, val in row.items():
        if not key.startswith("ratio") or key == "ratio_vs_BK0":
            continue
        suffix = key.replace("ratio", "")
        if not suffix.isdigit():
            continue
        if val == "":
            continue
        ratios[int(suffix)] = float(val)
    return ratios


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

    # per-topology plots (policies overlaid)
    for topo in topologies:
        for metric in metrics:
            plt.figure(figsize=(6, 4))
            for policy in policies:
                row = next(
                    (r for r in rows if r["topology_id"] == topo and r["policy"] == policy and r["metric"] == metric),
                    None,
                )
                if not row:
                    continue
                ratios = ratios_from_row(row)
                if not ratios:
                    continue
                xs = sorted(ratios.keys())
                ys = [ratios[k] for k in xs]
                plt.plot(xs, ys, marker="o", label=policy)
            plt.xlabel("upgrade_k")
            plt.ylabel("EQT/BK0 ratio")
            plt.title(f"{topo} ({metric})")
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(out_dir / f"{topo}_policy_ratio_{metric}.png")
            plt.close()

    # per-policy plots (topologies overlaid)
    for policy in policies:
        for metric in metrics:
            plt.figure(figsize=(6, 4))
            for topo in topologies:
                row = next(
                    (r for r in rows if r["topology_id"] == topo and r["policy"] == policy and r["metric"] == metric),
                    None,
                )
                if not row:
                    continue
                ratios = ratios_from_row(row)
                if not ratios:
                    continue
                xs = sorted(ratios.keys())
                ys = [ratios[k] for k in xs]
                plt.plot(xs, ys, marker="o", label=topo)
            plt.xlabel("upgrade_k")
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
            ratios_by_k: Dict[int, List[float]] = {}
            for row in rows:
                if row["policy"] != policy or row["metric"] != metric:
                    continue
                for k, v in ratios_from_row(row).items():
                    ratios_by_k.setdefault(k, []).append(v)
            for k in sorted(ratios_by_k.keys()):
                vals = ratios_by_k[k]
                pooled_rows.append(
                    {
                        "policy": policy,
                        "metric": metric,
                        "upgrade_k": k,
                        "ratio_median": float(np.median(vals)),
                        "ratio_worst": float(np.min(vals)),
                        "ratio_max": float(np.max(vals)),
                    }
                )
    pooled_path = out_dir / "policy_topology_pooled_ratios.csv"
    with pooled_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["policy", "metric", "upgrade_k", "ratio_median", "ratio_worst", "ratio_max"],
        )
        writer.writeheader()
        writer.writerows(pooled_rows)

    # curvature summary table
    curvature_rows = []
    for row in rows:
        c1 = float(row.get("c1", 0.0) or 0.0)
        c2 = float(row.get("c2", 0.0) or 0.0)
        curvature_rows.append(
            {
                "topology_id": row["topology_id"],
                "policy": row["policy"],
                "metric": row["metric"],
                "ratio21": row.get("ratio21", ""),
                "c1": c1,
                "c2": c2,
                "curve_shape": classify_curve(c1, c2),
            }
        )
    curvature_path = out_dir / "policy_topology_curvature_summary.csv"
    with curvature_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["topology_id", "policy", "metric", "ratio21", "c1", "c2", "curve_shape"],
        )
        writer.writeheader()
        writer.writerows(curvature_rows)

    print(f"Wrote {pooled_path}")
    print(f"Wrote {curvature_path}")


if __name__ == "__main__":
    main()
