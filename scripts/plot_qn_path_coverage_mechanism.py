"""Plot upgrade-path coverage mechanism across topologies."""

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
    p = argparse.ArgumentParser(description="Plot path coverage mechanism analysis.")
    p.add_argument("--analysis-dir", type=Path, required=True, help="Directory containing coverage CSVs.")
    p.add_argument("--workers", type=int, default=2, help="Worker count for CPU policy validation.")
    return p.parse_args()


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def main() -> None:
    args = parse_args()
    normalize_workers(args.workers, min_workers=2, max_workers=20)
    out_dir = args.analysis_dir / "plots_path_coverage"
    out_dir.mkdir(parents=True, exist_ok=True)

    join_path = args.analysis_dir / "path_coverage_join.csv"
    thresholds_path = args.analysis_dir / "path_coverage_thresholds.csv"
    if not join_path.exists() or not thresholds_path.exists():
        raise SystemExit("Missing path_coverage_join.csv or path_coverage_thresholds.csv; run analysis first.")

    join_rows = load_csv(join_path)
    thresholds = load_csv(thresholds_path)

    import matplotlib.pyplot as plt

    # Ratio vs path_upgraded_fraction, pooled by policy.
    policy_groups: Dict[str, List[Dict[str, str]]] = {}
    for r in join_rows:
        policy_groups.setdefault(r.get("upgrade_policy", ""), []).append(r)
    plt.figure()
    for policy, rows in sorted(policy_groups.items()):
        xs = []
        ys = []
        for r in rows:
            if r.get("path_upgraded_fraction") == "" or r.get("ratio_vs_bk0") == "":
                continue
            xs.append(float(r["path_upgraded_fraction"]))
            ys.append(float(r["ratio_vs_bk0"]))
        if xs:
            plt.scatter(xs, ys, label=policy, alpha=0.5)
    plt.xlabel("path_upgraded_fraction")
    plt.ylabel("ratio_vs_bk0")
    plt.title("Ratio vs path upgraded fraction")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "ratio_vs_path_upgraded_fraction.png", dpi=150)
    plt.close()

    # k* vs coverage threshold.
    xs = []
    ys = []
    colors = []
    policies = []
    for r in thresholds:
        if r.get("coverage_threshold_k") == "" or r.get("k_star") == "":
            continue
        xs.append(float(r["coverage_threshold_k"]))
        ys.append(float(r["k_star"]))
        policies.append(r.get("upgrade_policy", ""))
    plt.figure()
    for policy in sorted(set(policies)):
        idx = [i for i, p in enumerate(policies) if p == policy]
        plt.scatter([xs[i] for i in idx], [ys[i] for i in idx], label=policy, alpha=0.6)
    plt.xlabel("coverage_threshold_k")
    plt.ylabel("k_star")
    plt.title("k* vs coverage threshold k")
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_dir / "kstar_vs_coverage_threshold.png", dpi=150)
    plt.close()

    print(f"Wrote plots to {out_dir}")


if __name__ == "__main__":
    main()
