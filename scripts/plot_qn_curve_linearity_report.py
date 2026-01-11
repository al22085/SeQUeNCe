"""Plot straight-vs-curve report outputs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.parallel import normalize_workers


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot linearity report outputs.")
    p.add_argument("--root-dir", type=Path, required=True, help="Run root directory containing report CSVs.")
    p.add_argument("--workers", type=int, default=2, help="Worker count for CPU policy validation.")
    return p.parse_args()


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def main() -> None:
    args = parse_args()
    normalize_workers(args.workers, min_workers=2, max_workers=20)
    out_dir = args.root_dir / "plots_linearity"
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_path = args.root_dir / "line_vs_curve_summary.csv"
    k_star_path = args.root_dir / "k_star_table.csv"
    if not summary_path.exists() or not k_star_path.exists():
        raise SystemExit("Missing line_vs_curve_summary.csv or k_star_table.csv; run exporter first.")

    summary_rows = load_csv(summary_path)
    k_star_rows = load_csv(k_star_path)

    import matplotlib.pyplot as plt

    # Fraction nonlinear by policy.
    policy_rows = [r for r in summary_rows if r["scope"] == "policy"]
    policy_rows = sorted(policy_rows, key=lambda r: r["upgrade_policy"])
    policies = [r["upgrade_policy"] for r in policy_rows]
    frac_nl = [float(r["fraction_nonlinear"]) for r in policy_rows]
    plt.figure()
    plt.bar(policies, frac_nl)
    plt.ylabel("fraction_nonlinear")
    plt.title("Fraction nonlinear by policy")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / "fraction_nonlinear_by_policy.png", dpi=150)
    plt.close()

    # Fraction nonlinear by label.
    label_rows = [r for r in summary_rows if r["scope"] == "label"]
    label_rows = sorted(label_rows, key=lambda r: r["label"])
    labels = [r["label"] for r in label_rows]
    frac_nl = [float(r["fraction_nonlinear"]) for r in label_rows]
    plt.figure()
    plt.bar(labels, frac_nl)
    plt.ylabel("fraction_nonlinear")
    plt.title("Fraction nonlinear by distance label")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(out_dir / "fraction_nonlinear_by_label.png", dpi=150)
    plt.close()

    # k* distribution by policy.
    pair_rows = [r for r in k_star_rows if r["scope"] == "pair" and r.get("k_star_fraction") != ""]
    policy_to_vals: Dict[str, List[float]] = {}
    for r in pair_rows:
        policy_to_vals.setdefault(r["upgrade_policy"], []).append(float(r["k_star_fraction"]))
    if policy_to_vals:
        plt.figure()
        data = [policy_to_vals[p] for p in sorted(policy_to_vals.keys())]
        plt.boxplot(data, labels=sorted(policy_to_vals.keys()))
        plt.ylabel("k_star_fraction")
        plt.title("k* distribution by policy")
        plt.xticks(rotation=30, ha="right")
        plt.tight_layout()
        plt.savefig(out_dir / "k_star_fraction_by_policy.png", dpi=150)
        plt.close()

    # Curvature vs max ratio scatter.
    pair_rows = [r for r in summary_rows if r["scope"] == "topology_policy_label"]
    # Rebuild per-pair data from k_star table for max_ratio.
    max_ratio_by_pair: Dict[tuple, float] = {}
    for r in k_star_rows:
        if r["scope"] != "pair":
            continue
        key = (r["topology_id"], r["upgrade_policy"], r["pair"], r["label"])
        max_ratio_by_pair[key] = float(r["max_ratio"])

    # Need curve metrics for curvature and policy.
    curve_metrics = []
    for metrics_path in args.root_dir.glob("**/curve_metrics.csv"):
        curve_metrics.extend(load_csv(metrics_path))

    policy_colors: Dict[str, str] = {}
    plt.figure()
    for r in curve_metrics:
        key = (
            r.get("topology_id", ""),
            r.get("upgrade_policy", ""),
            r.get("pair", ""),
            r.get("label", "").split("_")[0],
        )
        max_ratio = max_ratio_by_pair.get(key)
        if max_ratio is None:
            continue
        policy = r.get("upgrade_policy", "")
        if policy not in policy_colors:
            policy_colors[policy] = None
        plt.scatter(float(r["curvature"]), max_ratio, label=policy)
    # De-duplicate legend entries.
    handles, labels = plt.gca().get_legend_handles_labels()
    seen = set()
    uniq_handles = []
    uniq_labels = []
    for h, l in zip(handles, labels):
        if l in seen:
            continue
        seen.add(l)
        uniq_handles.append(h)
        uniq_labels.append(l)
    if uniq_labels:
        plt.legend(uniq_handles, uniq_labels)
    plt.xlabel("curvature")
    plt.ylabel("max_ratio (EQT/BK0)")
    plt.title("Curvature vs max ratio")
    plt.tight_layout()
    plt.savefig(out_dir / "curvature_vs_max_ratio.png", dpi=150)
    plt.close()

    print(f"Wrote plots to {out_dir}")


if __name__ == "__main__":
    main()
