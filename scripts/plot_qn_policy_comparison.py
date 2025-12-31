"""Plot policy comparison upgrade-k curves and export curvature summary."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Plot upgrade policy comparison.")
    p.add_argument("--in-csv", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Policy comparison")
    return p.parse_args()


def load_rows(path: Path):
    with path.open() as f:
        return list(csv.DictReader(f))


def classify_curve(c1: float, c2: float) -> str:
    if max(abs(c1), abs(c2)) < 0.01:
        return "linear-ish"
    return "threshold"


def main():
    args = parse_args()
    rows = load_rows(args.in_csv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    policies = sorted({r["policy"] for r in rows})
    upgrade_vals = sorted({int(r["upgrade_k"]) for r in rows})

    # plot median ratio vs upgrade_k per policy
    plt.figure(figsize=(6, 4))
    for policy in policies:
        xs, ys = [], []
        for uk in upgrade_vals:
            vals = [
                float(r["ratio_vs_BK0"])
                for r in rows
                if r["policy"] == policy and int(r["upgrade_k"]) == uk
            ]
            if not vals:
                continue
            xs.append(uk)
            ys.append(float(np.median(vals)))
        if xs:
            plt.plot(xs, ys, marker="o", label=policy)
    plt.xlabel("upgrade_k")
    plt.ylabel("EQT/BK0 ratio (median)")
    plt.title(args.title)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(args.out_dir / "policy_ratio_median.png")
    plt.close()

    # worst-case ratio per policy (min)
    plt.figure(figsize=(6, 4))
    for policy in policies:
        xs, ys = [], []
        for uk in upgrade_vals:
            vals = [
                float(r["ratio_vs_BK0"])
                for r in rows
                if r["policy"] == policy and int(r["upgrade_k"]) == uk
            ]
            if not vals:
                continue
            xs.append(uk)
            ys.append(float(np.min(vals)))
        if xs:
            plt.plot(xs, ys, marker="o", label=policy)
    plt.xlabel("upgrade_k")
    plt.ylabel("EQT/BK0 ratio (worst-case)")
    plt.title(args.title)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(args.out_dir / "policy_ratio_worst.png")
    plt.close()

    # curvature table
    summary_rows = []
    for policy in policies:
        # use any row (same for all rows for a policy)
        sample = next((r for r in rows if r["policy"] == policy), None)
        if not sample:
            continue
        c1 = float(sample["c1"])
        c2 = float(sample["c2"])
        summary_rows.append(
            {
                "policy": policy,
                "s03": sample["s03"],
                "s37": sample["s37"],
                "s721": sample["s721"],
                "c1": c1,
                "c2": c2,
                "curve_shape": classify_curve(c1, c2),
            }
        )
    summary_path = args.out_dir / "policy_curvature_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["policy", "s03", "s37", "s721", "c1", "c2", "curve_shape"],
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
