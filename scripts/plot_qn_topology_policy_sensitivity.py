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

    # load curve points (per-pair and aggregated)
    curve_points = []
    for path in args.root_dir.glob(args.curve_points_glob):
        curve_points.extend(load_rows(path))

    # aggregate by label (short/medium/long) for median/worst-case across pairs
    label_points: Dict[tuple, Dict[float, List[float]]] = {}
    for p in curve_points:
        if p["pair"] in ("median", "worst_case"):
            continue
        label = p.get("label", "")
        if not label:
            continue
        key = (p.get("topology_id", ""), p.get("upgrade_policy", ""), label)
        frac = float(p["upgraded_fraction"])
        label_points.setdefault(key, {}).setdefault(frac, []).append(float(p["ratio_vs_bk0"]))

    def summarize(vals: List[float], metric: str) -> float:
        if metric == "worst_case":
            return float(np.min(vals))
        return float(np.median(vals))

    # per-topology, per-label plots (policies overlaid)
    for topo in topologies:
        for label in sorted({p.get("label", "") for p in curve_points if p.get("topology_id") == topo and p.get("label")}):
            for metric in metrics:
                plt.figure(figsize=(6, 4))
                for policy in policies:
                    key = (topo, policy, label)
                    if key not in label_points:
                        continue
                    frac_map = label_points[key]
                    xs = sorted(frac_map.keys())
                    ys = [summarize(frac_map[x], metric) for x in xs]
                    plt.plot(xs, ys, marker="o", label=policy)
                plt.xlabel("upgraded_fraction (k/Kmax)")
                plt.ylabel("EQT/BK0 ratio")
                plt.title(f"{topo} {label} ({metric})")
                plt.legend()
                plt.grid(True, alpha=0.3)
                plt.tight_layout()
                plt.savefig(out_dir / f"{topo}_{label}_policy_ratio_{metric}.png")
                plt.close()

    # per-policy, per-label plots (topologies overlaid)
    for policy in policies:
        for label in sorted({p.get("label", "") for p in curve_points if p.get("label")}):
            for metric in metrics:
                plt.figure(figsize=(6, 4))
                for topo in topologies:
                    key = (topo, policy, label)
                    if key not in label_points:
                        continue
                    frac_map = label_points[key]
                    xs = sorted(frac_map.keys())
                    ys = [summarize(frac_map[x], metric) for x in xs]
                    plt.plot(xs, ys, marker="o", label=topo)
                plt.xlabel("upgraded_fraction (k/Kmax)")
                plt.ylabel("EQT/BK0 ratio")
                plt.title(f"{policy} {label} ({metric})")
                plt.legend()
                plt.grid(True, alpha=0.3)
                plt.tight_layout()
                plt.savefig(out_dir / f"{policy}_{label}_topology_ratio_{metric}.png")
                plt.close()

    # pooled summary across topologies by label
    pooled_rows = []
    for policy in policies:
        for metric in metrics:
            for label in sorted({p.get("label", "") for p in curve_points if p.get("label")}):
                ratios_by_frac: Dict[float, List[float]] = {}
                for p in curve_points:
                    if p["pair"] in ("median", "worst_case"):
                        continue
                    if p.get("upgrade_policy", "") != policy:
                        continue
                    if p.get("label", "") != label:
                        continue
                    frac = float(p["upgraded_fraction"])
                    ratios_by_frac.setdefault(frac, []).append(float(p["ratio_vs_bk0"]))
                for frac in sorted(ratios_by_frac.keys()):
                    vals = ratios_by_frac[frac]
                    pooled_rows.append(
                        {
                            "policy": policy,
                            "metric": metric,
                            "label": label,
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
            fieldnames=["policy", "metric", "label", "upgraded_fraction", "ratio_median", "ratio_worst", "ratio_max"],
        )
        writer.writeheader()
        writer.writerows(pooled_rows)

    # curvature/key table per topology+policy+label
    def fit_metrics(xs: List[float], ys: List[float]) -> Dict[str, float]:
        if len(xs) < 2:
            return {"r2": 1.0, "curvature": 0.0}
        x = np.array(xs, dtype=float)
        y = np.array(ys, dtype=float)
        coeffs = np.polyfit(x, y, 1)
        y_hat = np.polyval(coeffs, x)
        ss_res = float(np.sum((y - y_hat) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1.0 if ss_tot == 0 else 1.0 - ss_res / ss_tot
        if len(ys) >= 3:
            second = [y[i + 1] - 2 * y[i] + y[i - 1] for i in range(1, len(y) - 1)]
            curvature = float(np.mean(np.abs(second)))
        else:
            curvature = 0.0
        return {"r2": r2, "curvature": curvature}

    key_rows = []
    for topo in topologies:
        for policy in policies:
            for label in sorted({p.get("label", "") for p in curve_points if p.get("label")}):
                key = (topo, policy, label)
                if key not in label_points:
                    continue
                frac_map = label_points[key]
                xs = sorted(frac_map.keys())
                ys_med = [summarize(frac_map[x], "median") for x in xs]
                metrics_fit = fit_metrics(xs, ys_med)
                max_ratio = max(ys_med) if ys_med else 0.0
                max_frac = xs[ys_med.index(max_ratio)] if ys_med else 0.0
                classification = (
                    "approximately_linear"
                    if metrics_fit["r2"] >= 0.98 and metrics_fit["curvature"] <= 0.01
                    else "nonlinear"
                )
                key_rows.append(
                    {
                        "topology_id": topo,
                        "policy": policy,
                        "label": label,
                        "r2": metrics_fit["r2"],
                        "curvature": metrics_fit["curvature"],
                        "classification": classification,
                        "max_ratio": max_ratio,
                        "max_upgraded_fraction": max_frac,
                    }
                )
    key_path = out_dir / "policy_topology_distance_curve_summary.csv"
    with key_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "topology_id",
                "policy",
                "label",
                "r2",
                "curvature",
                "classification",
                "max_ratio",
                "max_upgraded_fraction",
            ],
        )
        writer.writeheader()
        writer.writerows(key_rows)

    print(f"Wrote {pooled_path}")
    print(f"Wrote {key_path}")


if __name__ == "__main__":
    main()
