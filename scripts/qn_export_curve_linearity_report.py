"""Export straight-vs-curve summary from curve points/metrics for a completed run."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.parallel import normalize_workers


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export line-vs-curve summaries from curve points/metrics.")
    p.add_argument("--root-dir", type=Path, required=True, help="Completed run root directory.")
    p.add_argument("--ratio-threshold", type=float, default=1.05, help="Threshold for k* (ratio>=threshold).")
    p.add_argument("--out-dir", type=Path, default=None, help="Output directory (default: root-dir).")
    p.add_argument("--workers", type=int, default=2, help="Worker count for CPU policy validation.")
    return p.parse_args()


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Iterable[Dict[str, object]], fieldnames: List[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def label_base(raw: str) -> str:
    if not raw:
        return ""
    return raw.split("_")[0]


def median(values: List[float]) -> float:
    return statistics.median(values) if values else float("nan")


def iqr(values: List[float]) -> float:
    if not values:
        return float("nan")
    if len(values) < 2:
        return 0.0
    values_sorted = sorted(values)
    q1 = statistics.quantiles(values_sorted, n=4, method="inclusive")[0]
    q3 = statistics.quantiles(values_sorted, n=4, method="inclusive")[2]
    return q3 - q1


def find_curve_files(root_dir: Path) -> List[Tuple[Path, Path]]:
    pairs = []
    for curve_points in root_dir.glob("**/curve_points.csv"):
        curve_metrics = curve_points.with_name("curve_metrics.csv")
        if curve_metrics.exists():
            pairs.append((curve_points, curve_metrics))
    return pairs


def main() -> None:
    args = parse_args()
    normalize_workers(args.workers, min_workers=2, max_workers=20)
    out_dir = args.out_dir or args.root_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    curve_pairs = find_curve_files(args.root_dir)
    if not curve_pairs:
        raise SystemExit(f"No curve_points.csv found under {args.root_dir}")

    curve_points_rows: List[Dict[str, str]] = []
    curve_metrics_rows: List[Dict[str, str]] = []
    for points_path, metrics_path in curve_pairs:
        curve_points_rows.extend(load_csv(points_path))
        curve_metrics_rows.extend(load_csv(metrics_path))

    # Max ratio per pair.
    max_ratio_by_pair: Dict[Tuple[str, str, str, str], float] = {}
    for r in curve_points_rows:
        key = (
            r.get("topology_id", ""),
            r.get("upgrade_policy", ""),
            r.get("pair", ""),
            label_base(r.get("label", "")),
        )
        ratio = float(r.get("ratio_vs_bk0", "nan"))
        prev = max_ratio_by_pair.get(key, float("-inf"))
        if ratio > prev:
            max_ratio_by_pair[key] = ratio

    # Summary by topology/policy/label.
    grouped: Dict[Tuple[str, str, str], List[Dict[str, str]]] = {}
    for r in curve_metrics_rows:
        key = (r.get("topology_id", ""), r.get("upgrade_policy", ""), label_base(r.get("label", "")))
        grouped.setdefault(key, []).append(r)

    summary_rows: List[Dict[str, object]] = []
    for (topo, policy, lbl), rows in sorted(grouped.items()):
        r2s = [float(r["r2"]) for r in rows]
        curvs = [float(r["curvature"]) for r in rows]
        nonlinear = sum(1 for r in rows if r.get("classification") != "approximately_linear")
        max_ratios = [
            max_ratio_by_pair.get((topo, policy, r.get("pair", ""), lbl), float("nan")) for r in rows
        ]
        summary_rows.append(
            {
                "scope": "topology_policy_label",
                "topology_id": topo,
                "upgrade_policy": policy,
                "label": lbl,
                "n_pairs": len(rows),
                "fraction_nonlinear": nonlinear / len(rows) if rows else float("nan"),
                "median_r2": median(r2s),
                "median_curvature": median(curvs),
                "worst_curvature": max(curvs) if curvs else float("nan"),
                "median_max_ratio": median(max_ratios),
                "max_max_ratio": max(max_ratios) if max_ratios else float("nan"),
            }
        )

    # Pooled by policy.
    by_policy: Dict[str, List[Dict[str, str]]] = {}
    for r in curve_metrics_rows:
        by_policy.setdefault(r.get("upgrade_policy", ""), []).append(r)
    for policy, rows in sorted(by_policy.items()):
        r2s = [float(r["r2"]) for r in rows]
        curvs = [float(r["curvature"]) for r in rows]
        nonlinear = sum(1 for r in rows if r.get("classification") != "approximately_linear")
        max_ratios = [
            max_ratio_by_pair.get(
                (r.get("topology_id", ""), policy, r.get("pair", ""), label_base(r.get("label", ""))),
                float("nan"),
            )
            for r in rows
        ]
        summary_rows.append(
            {
                "scope": "policy",
                "topology_id": "",
                "upgrade_policy": policy,
                "label": "",
                "n_pairs": len(rows),
                "fraction_nonlinear": nonlinear / len(rows) if rows else float("nan"),
                "median_r2": median(r2s),
                "median_curvature": median(curvs),
                "worst_curvature": max(curvs) if curvs else float("nan"),
                "median_max_ratio": median(max_ratios),
                "max_max_ratio": max(max_ratios) if max_ratios else float("nan"),
            }
        )

    # Pooled by distance label.
    by_label: Dict[str, List[Dict[str, str]]] = {}
    for r in curve_metrics_rows:
        by_label.setdefault(label_base(r.get("label", "")), []).append(r)
    for lbl, rows in sorted(by_label.items()):
        r2s = [float(r["r2"]) for r in rows]
        curvs = [float(r["curvature"]) for r in rows]
        nonlinear = sum(1 for r in rows if r.get("classification") != "approximately_linear")
        max_ratios = [
            max_ratio_by_pair.get(
                (r.get("topology_id", ""), r.get("upgrade_policy", ""), r.get("pair", ""), lbl),
                float("nan"),
            )
            for r in rows
        ]
        summary_rows.append(
            {
                "scope": "label",
                "topology_id": "",
                "upgrade_policy": "",
                "label": lbl,
                "n_pairs": len(rows),
                "fraction_nonlinear": nonlinear / len(rows) if rows else float("nan"),
                "median_r2": median(r2s),
                "median_curvature": median(curvs),
                "worst_curvature": max(curvs) if curvs else float("nan"),
                "median_max_ratio": median(max_ratios),
                "max_max_ratio": max(max_ratios) if max_ratios else float("nan"),
            }
        )

    summary_path = out_dir / "line_vs_curve_summary.csv"
    write_csv(
        summary_path,
        summary_rows,
        [
            "scope",
            "topology_id",
            "upgrade_policy",
            "label",
            "n_pairs",
            "fraction_nonlinear",
            "median_r2",
            "median_curvature",
            "worst_curvature",
            "median_max_ratio",
            "max_max_ratio",
        ],
    )
    print(f"Wrote {summary_path}")

    # k* table.
    ratio_threshold = args.ratio_threshold
    k_star_rows: List[Dict[str, object]] = []
    per_pair: Dict[Tuple[str, str, str, str], List[Dict[str, str]]] = {}
    for r in curve_points_rows:
        key = (
            r.get("topology_id", ""),
            r.get("upgrade_policy", ""),
            r.get("pair", ""),
            label_base(r.get("label", "")),
        )
        per_pair.setdefault(key, []).append(r)
    for (topo, policy, pair, lbl), rows in sorted(per_pair.items()):
        rows_sorted = sorted(rows, key=lambda r: int(r["upgrade_k"]))
        kmax = max(int(r["upgrade_k"]) for r in rows_sorted)
        k_star = None
        for r in rows_sorted:
            if float(r["ratio_vs_bk0"]) >= ratio_threshold:
                k_star = int(r["upgrade_k"])
                break
        max_ratio = max(float(r["ratio_vs_bk0"]) for r in rows_sorted)
        k_star_rows.append(
            {
                "scope": "pair",
                "topology_id": topo,
                "upgrade_policy": policy,
                "label": lbl,
                "pair": pair,
                "kmax": kmax,
                "k_star": k_star if k_star is not None else "",
                "k_star_fraction": (k_star / kmax) if k_star is not None else "",
                "max_ratio": max_ratio,
            }
        )

    # Pooled by policy and label.
    def pooled_kstar(scope: str, key_val: str, rows: List[Dict[str, object]]) -> Dict[str, object]:
        kstars = [float(r["k_star"]) for r in rows if r.get("k_star") != ""]
        kstar_frac = [float(r["k_star_fraction"]) for r in rows if r.get("k_star_fraction") != ""]
        max_ratios = [float(r["max_ratio"]) for r in rows]
        return {
            "scope": scope,
            "topology_id": "",
            "upgrade_policy": key_val if scope == "policy" else "",
            "label": key_val if scope == "label" else "",
            "pair": "",
            "kmax": "",
            "k_star": median(kstars),
            "k_star_fraction": median(kstar_frac),
            "max_ratio": median(max_ratios),
            "k_star_iqr": iqr(kstars),
            "k_star_fraction_iqr": iqr(kstar_frac),
        }

    by_policy_rows: Dict[str, List[Dict[str, object]]] = {}
    by_label_rows: Dict[str, List[Dict[str, object]]] = {}
    for r in k_star_rows:
        by_policy_rows.setdefault(str(r["upgrade_policy"]), []).append(r)
        by_label_rows.setdefault(str(r["label"]), []).append(r)

    pooled_rows: List[Dict[str, object]] = []
    for policy, rows in sorted(by_policy_rows.items()):
        pooled_rows.append(pooled_kstar("policy", policy, rows))
    for lbl, rows in sorted(by_label_rows.items()):
        pooled_rows.append(pooled_kstar("label", lbl, rows))

    k_star_path = out_dir / "k_star_table.csv"
    fieldnames = [
        "scope",
        "topology_id",
        "upgrade_policy",
        "label",
        "pair",
        "kmax",
        "k_star",
        "k_star_fraction",
        "max_ratio",
        "k_star_iqr",
        "k_star_fraction_iqr",
    ]
    write_csv(k_star_path, k_star_rows + pooled_rows, fieldnames)
    print(f"Wrote {k_star_path}")

    # Markdown report.
    policy_summaries = [r for r in summary_rows if r["scope"] == "policy"]
    label_summaries = [r for r in summary_rows if r["scope"] == "label"]
    kstar_policies = [r for r in pooled_rows if r["scope"] == "policy"]

    lines = []
    lines.append("# Line vs Curve Summary")
    lines.append("")
    lines.append("Metrics: R^2 from linear fit of ratio vs upgraded_fraction; curvature is mean |second-diff|.")
    lines.append(f"k* is the smallest k where ratio >= {ratio_threshold}.")
    lines.append("")
    lines.append("## Fraction nonlinear by policy")
    for r in policy_summaries:
        lines.append(
            f"- {r['upgrade_policy']}: fraction_nonlinear={r['fraction_nonlinear']:.2f}, "
            f"median_r2={r['median_r2']:.3f}, median_curvature={r['median_curvature']:.4f}"
        )
    lines.append("")
    lines.append("## Fraction nonlinear by distance label")
    for r in label_summaries:
        lines.append(
            f"- {r['label']}: fraction_nonlinear={r['fraction_nonlinear']:.2f}, "
            f"median_r2={r['median_r2']:.3f}, median_curvature={r['median_curvature']:.4f}"
        )
    lines.append("")
    lines.append("## k* (ratio threshold) by policy")
    for r in kstar_policies:
        lines.append(
            f"- {r['upgrade_policy']}: k* median={r['k_star']}, "
            f"k*/kmax median={r['k_star_fraction']}"
        )
    report_path = out_dir / "line_vs_curve_report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {report_path}")


if __name__ == "__main__":
    main()
