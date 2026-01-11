"""Generate a concise markdown key-findings summary from computed CSVs."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Dict, List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate paper_key_findings.md from computed CSVs.")
    p.add_argument("--root-dir", type=Path, required=True, help="Run root directory.")
    p.add_argument("--analysis-dir", type=Path, default=None, help="Path coverage analysis directory.")
    p.add_argument(
        "--out-path",
        type=Path,
        default=None,
        help="Markdown output path (default: <root>/plots_linearity/paper_key_findings.md).",
    )
    return p.parse_args()


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def median(values: List[float]) -> float:
    return statistics.median(values) if values else float("nan")


def main() -> None:
    args = parse_args()
    root = args.root_dir
    analysis_dir = args.analysis_dir or (root / "analysis_path_coverage")
    out_path = args.out_path or (root / "plots_linearity" / "paper_key_findings.md")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    summary_path = root / "line_vs_curve_summary.csv"
    if not summary_path.exists():
        raise SystemExit(f"Missing {summary_path}; run qn_export_curve_linearity_report.py first.")
    summary_rows = load_csv(summary_path)

    coverage_summary_path = analysis_dir / "path_coverage_thresholds_summary.csv"
    coverage_rows = load_csv(coverage_summary_path) if coverage_summary_path.exists() else []

    # Missing pair visibility.
    missing_by_topo: Dict[str, Dict[str, int]] = {}
    tol_summary_path = root / "tolerance_missing_summary.csv"
    tol_summary_rows = load_csv(tol_summary_path) if tol_summary_path.exists() else []
    for topo_dir in sorted(root.iterdir()):
        if not topo_dir.is_dir():
            continue
        pairs_csv = topo_dir / "pairs_repr3.csv"
        if not pairs_csv.exists():
            continue
        rows = load_csv(pairs_csv)
        for r in rows:
            if r.get("found", "").lower() in ("false", "0"):
                topo = r.get("topology_id") or topo_dir.name
                label = r.get("label", "")
                base = label.split("_")[0] if label else ""
                missing_by_topo.setdefault(topo, {})
                missing_by_topo[topo][base] = missing_by_topo[topo].get(base, 0) + 1

    def fmt_rows(rows: List[Dict[str, str]]) -> List[str]:
        lines = []
        for r in rows:
            lines.append(
                f"- policy={r.get('upgrade_policy','') or 'all'} "
                f"label={r.get('label','') or 'all'} "
                f"fraction_nonlinear={r.get('fraction_nonlinear','')} "
                f"median_r2={r.get('median_r2','')} "
                f"median_curvature={r.get('median_curvature','')}"
            )
        return lines

    policy_rows = [r for r in summary_rows if r["scope"] == "policy"]
    label_rows = [r for r in summary_rows if r["scope"] == "label"]

    coverage_policy = [r for r in coverage_rows if r.get("scope") == "policy"]
    coverage_label = [r for r in coverage_rows if r.get("scope") == "label"]

    lines: List[str] = []
    lines.append("# Paper Key Findings (computed)")
    lines.append("")
    lines.append("## Line vs Curve (policy)")
    lines.extend(fmt_rows(policy_rows))
    lines.append("")
    lines.append("## Line vs Curve (distance label)")
    lines.extend(fmt_rows(label_rows))
    lines.append("")
    if coverage_rows:
        lines.append("## Path coverage thresholds (policy)")
        for r in coverage_policy:
            lines.append(
                f"- policy={r.get('upgrade_policy','')} "
                f"coverage_threshold_k_median={r.get('coverage_threshold_k_median','')} "
                f"k_star_median={r.get('k_star_median','')}"
            )
        lines.append("")
        lines.append("## Path coverage thresholds (distance label)")
        for r in coverage_label:
            lines.append(
                f"- label={r.get('label','')} "
                f"coverage_threshold_k_median={r.get('coverage_threshold_k_median','')} "
                f"k_star_median={r.get('k_star_median','')}"
            )
        lines.append("")
    else:
        lines.append("## Path coverage thresholds")
        lines.append("- No path coverage summary found.")
        lines.append("")

    lines.append("## Missing representative pairs")
    if not missing_by_topo:
        lines.append("- None (all targets satisfied within tolerance).")
    else:
        for topo_id, counts in sorted(missing_by_topo.items()):
            details = ", ".join([f"{k}:{v}" for k, v in sorted(counts.items())])
            lines.append(f"- {topo_id}: missing_pairs={details}")
    if tol_summary_rows:
        lines.append("")
        lines.append("## Missing pairs summary (tolerance sweep)")
        for r in tol_summary_rows:
            if r.get("topology_id") != "ALL_TOPOLOGIES" or r.get("label") != "all":
                continue
            lines.append(
                f"- tol={r.get('tolerance')} "
                f"missing_count={r.get('missing_count')} "
                f"completeness={r.get('completeness')}"
            )

    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
