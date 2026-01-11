"""Export Tier2 paper artifacts (tables/figures/README) from computed outputs."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export Tier2 paper artifacts from computed outputs.")
    p.add_argument("--root-dir", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, default=None)
    return p.parse_args()


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def write_tex_table(path: Path, headers: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    cols = " | ".join(["l"] * len(headers))
    lines = [r"\begin{tabular}{" + cols.replace(" | ", "") + r"}", r"\hline"]
    lines.append(" & ".join(headers) + r" \\")
    lines.append(r"\hline")
    for row in rows:
        lines.append(" & ".join(row) + r" \\")
    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    path.write_text("\n".join(lines) + "\n")


def unique_sorted(values: Sequence[str]) -> List[str]:
    return sorted({v for v in values if v})


def find_seed_list(root: Path) -> List[int]:
    for path in root.rglob("robust_frontier_raw.csv"):
        rows = load_csv(path)
        if not rows or "seed" not in rows[0]:
            continue
        seeds = sorted({int(r["seed"]) for r in rows if r.get("seed")})
        if seeds:
            return seeds
    return []


def build_run_metadata(root: Path) -> Dict[str, object]:
    meta_path = root / "run_metadata.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())

    chosen_tol_path = root / "chosen_tolerance.json"
    summary_path = root / "summary_upgrade_curves.csv"
    summary_rows = load_csv(summary_path) if summary_path.exists() else []
    policies = unique_sorted([r.get("policy", "") for r in summary_rows])
    targets = unique_sorted([r.get("target_A", "") for r in summary_rows])
    kbits = unique_sorted([r.get("kbits", "") for r in summary_rows])
    eta = unique_sorted([r.get("eta", "") for r in summary_rows])
    seeds = find_seed_list(root)

    chosen = json.loads(chosen_tol_path.read_text()) if chosen_tol_path.exists() else {}
    targets_km = chosen.get("targets_km", [])
    pairs_per_target = chosen.get("pairs_per_target")
    chosen_topologies = chosen.get("chosen_topologies", [])
    chosen_tolerance = chosen.get("chosen_tolerance")

    meta = {
        "chosen_tolerance": chosen_tolerance,
        "targets_km": targets_km,
        "pairs_per_target": pairs_per_target,
        "chosen_topologies": chosen_topologies,
        "policies": policies,
        "target_A_values": targets,
        "kbits_values": kbits,
        "eta_values": eta,
        "seeds": seeds,
    }
    meta_path.write_text(json.dumps(meta, indent=2))
    return meta


def ensure_plot(root: Path, plot_script: Path, args: List[str], expected: Path) -> None:
    if expected.exists():
        return
    cmd = ["python", str(plot_script)] + args
    subprocess.run(cmd, check=True)


def copy_if_exists(src: Path, dst: Path) -> Optional[Path]:
    if not src.exists():
        return None
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def write_latex_shim(latex_dir: Path) -> None:
    latex_dir.mkdir(parents=True, exist_ok=True)
    shim_path = latex_dir / "tier2_paper_artifacts.tex"
    shim_lines = [
        "% Tier2 paper artifacts shim (requires graphicx).",
        "\\newcommand{\\TierTwoArtifactsRoot}{../}",
        "\\newcommand{\\TierTwoTableLinearityPath}{../tables/table_linearity_summary.tex}",
        "\\newcommand{\\TierTwoCoverageThresholdsPath}{../tables/table_coverage_thresholds.tex}",
        "\\newcommand{\\TierTwoRunMetadataPath}{../tables/table_run_metadata.tex}",
        "\\newcommand{\\TierTwoFigLinearityPath}{../figs/fig_linearity_overview.png}",
        "\\newcommand{\\TierTwoFigPathCoveragePath}{../figs/fig_path_coverage_overview.png}",
        "\\newcommand{\\TierTwoFigPolicyCurvesPath}{../figs/fig_policy_curves_overview.png}",
        "",
        "\\newcommand{\\TierTwoLinearityTable}{\\input{\\TierTwoTableLinearityPath}}",
        "\\newcommand{\\TierTwoCoverageThresholdsTable}{\\input{\\TierTwoCoverageThresholdsPath}}",
        "\\newcommand{\\TierTwoRunMetadataTable}{\\input{\\TierTwoRunMetadataPath}}",
        "",
        "\\newcommand{\\TierTwoFigLinearity}{\\includegraphics[width=\\linewidth]{\\TierTwoFigLinearityPath}}",
        "\\newcommand{\\TierTwoFigPathCoverage}{\\includegraphics[width=\\linewidth]{\\TierTwoFigPathCoveragePath}}",
        "\\newcommand{\\TierTwoFigPolicyCurves}{\\includegraphics[width=\\linewidth]{\\TierTwoFigPolicyCurvesPath}}",
        "",
    ]
    shim_path.write_text("\n".join(shim_lines))

    example_path = latex_dir / "example.tex"
    example_lines = [
        "\\documentclass{article}",
        "\\usepackage{graphicx}",
        "\\input{tier2_paper_artifacts}",
        "\\begin{document}",
        "\\section*{Tier2 Artifacts Example}",
        "\\TierTwoLinearityTable",
        "\\TierTwoCoverageThresholdsTable",
        "\\TierTwoRunMetadataTable",
        "\\TierTwoFigLinearity",
        "\\TierTwoFigPathCoverage",
        "\\TierTwoFigPolicyCurves",
        "\\end{document}",
        "",
    ]
    example_path.write_text("\n".join(example_lines))


def main() -> None:
    args = parse_args()
    root = args.root_dir
    out_dir = args.out_dir or (root / "paper_artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    figures_dir = out_dir / "figures"
    figs_dir = out_dir / "figs"
    tables_dir = out_dir / "tables"
    figures_dir.mkdir(parents=True, exist_ok=True)
    figs_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)

    summary_path = root / "line_vs_curve_summary.csv"
    coverage_path = root / "analysis_path_coverage" / "path_coverage_thresholds_summary.csv"
    if not summary_path.exists():
        raise SystemExit(f"Missing {summary_path}; run qn_export_curve_linearity_report.py first.")
    if not coverage_path.exists():
        raise SystemExit(f"Missing {coverage_path}; run qn_analyze_path_coverage_across_topologies.py first.")

    # Ensure plots exist, then copy with stable names.
    plots_linearity = root / "plots_linearity"
    plots_path_coverage = root / "analysis_path_coverage" / "plots_path_coverage"
    ensure_plot(
        root,
        Path("scripts/plot_qn_curve_linearity_report.py"),
        ["--root-dir", str(root), "--workers", "2"],
        plots_linearity / "fraction_nonlinear_by_policy.png",
    )
    ensure_plot(
        root,
        Path("scripts/plot_qn_path_coverage_mechanism.py"),
        ["--analysis-dir", str(root / "analysis_path_coverage"), "--workers", "2"],
        plots_path_coverage / "ratio_vs_path_upgraded_fraction.png",
    )

    fig_linearity = copy_if_exists(
        plots_linearity / "fraction_nonlinear_by_policy.png",
        figures_dir / "fig_linearity_overview.png",
    )
    fig_path_cov = copy_if_exists(
        plots_path_coverage / "ratio_vs_path_upgraded_fraction.png",
        figures_dir / "fig_path_coverage_overview.png",
    )
    policy_curve = plots_linearity / "curvature_vs_max_ratio.png"
    fig_policy = copy_if_exists(policy_curve, figures_dir / "fig_policy_curves_overview.png")

    for src in [fig_linearity, fig_path_cov, fig_policy]:
        if not src:
            continue
        copy_if_exists(src, figs_dir / Path(src).name)

    # Generate paper_key_findings if missing.
    key_findings = plots_linearity / "paper_key_findings.md"
    if not key_findings.exists():
        subprocess.run(
            [
                "python",
                "scripts/qn_generate_paper_key_findings.py",
                "--root-dir",
                str(root),
                "--analysis-dir",
                str(root / "analysis_path_coverage"),
            ],
            check=True,
        )
    key_dst = out_dir / "paper_key_findings.md"
    shutil.copy2(key_findings, key_dst)

    # Append run completeness using validation report if present.
    validation_path = out_dir / "validation_report.json"
    if validation_path.exists():
        report = json.loads(validation_path.read_text())
        missing = report.get("missing_pairs", {})
        preflight = report.get("preflight", {})
        with key_dst.open("a") as f:
            f.write("\n## Run completeness\n")
            f.write(
                f"- missing_total={missing.get('missing_total')} "
                f"missing_long={missing.get('missing_long')}\n"
            )
            f.write(
                f"- preflight_active_workers={preflight.get('active_workers')} "
                f"aggregate_cpu={preflight.get('aggregate_cpu')} "
                f"expected_cpu={preflight.get('expected_cpu')}\n"
            )

    # Tables.
    summary_rows = load_csv(summary_path)
    coverage_rows = load_csv(coverage_path)
    policy_rows = [r for r in summary_rows if r.get("scope") == "policy"]
    policy_rows = sorted(policy_rows, key=lambda r: r.get("upgrade_policy", ""))
    table_linearity = [
        [
            r.get("upgrade_policy", ""),
            r.get("fraction_nonlinear", ""),
            r.get("median_r2", ""),
            r.get("median_curvature", ""),
        ]
        for r in policy_rows
    ]
    write_tex_table(
        tables_dir / "table_linearity_summary.tex",
        ["policy", "fraction_nonlinear", "median_r2", "median_curvature"],
        table_linearity,
    )

    coverage_policy = [r for r in coverage_rows if r.get("scope") == "policy"]
    coverage_policy = sorted(coverage_policy, key=lambda r: r.get("upgrade_policy", ""))
    table_coverage = [
        [
            r.get("upgrade_policy", ""),
            r.get("coverage_threshold_k_median", ""),
            r.get("k_star_median", ""),
        ]
        for r in coverage_policy
    ]
    write_tex_table(
        tables_dir / "table_coverage_thresholds.tex",
        ["policy", "coverage_threshold_k_median", "k_star_median"],
        table_coverage,
    )

    meta = build_run_metadata(root)
    meta_rows = [
        ("chosen_tolerance", str(meta.get("chosen_tolerance"))),
        ("targets_km", ",".join([str(x) for x in meta.get("targets_km", [])])),
        ("pairs_per_target", str(meta.get("pairs_per_target"))),
        ("chosen_topologies", ",".join(meta.get("chosen_topologies", []))),
        ("policies", ",".join(meta.get("policies", []))),
        ("target_A_values", ",".join(meta.get("target_A_values", []))),
        ("kbits_values", ",".join(meta.get("kbits_values", []))),
        ("eta_values", ",".join(meta.get("eta_values", []))),
        ("seeds", ",".join([str(s) for s in meta.get("seeds", [])])),
    ]
    write_tex_table(
        tables_dir / "table_run_metadata.tex",
        ["key", "value"],
        [[k, v] for k, v in meta_rows],
    )

    readme = out_dir / "README.md"
    lines = [
        "# Tier2 Paper Artifacts",
        "",
        "## Contents",
        "- tables/: LaTeX tables for the paper.",
        "- figures/: Stable-named plots for the paper.",
        "- paper_key_findings.md: computed summary (no speculation).",
        "- validation_report.json: pass/fail and key checks.",
        "",
        "## Tables",
        "- table_linearity_summary.tex: policy -> fraction_nonlinear, median_r2, median_curvature.",
        "- table_coverage_thresholds.tex: policy -> coverage_threshold_k_median, k_star_median.",
        "- table_run_metadata.tex: run configuration (tolerance, targets, policies, seeds).",
        "",
        "## Figures",
        "- figs/fig_linearity_overview.png: fraction_nonlinear by policy.",
        "- figs/fig_path_coverage_overview.png: ratio vs path_upgraded_fraction.",
        "- figs/fig_policy_curves_overview.png: optional policy curves (if available).",
        "",
        "## LaTeX include shim",
        "1) \\usepackage{graphicx}",
        "2) \\input{paper_artifacts/latex_include/tier2_paper_artifacts.tex}",
        "3) Use macros: \\TierTwoLinearityTable, \\TierTwoCoverageThresholdsTable,",
        "   \\TierTwoRunMetadataTable, \\TierTwoFigLinearity, \\TierTwoFigPathCoverage,",
        "   \\TierTwoFigPolicyCurves.",
        "",
        "## Notes",
        "All outputs are generated from computed CSVs under the Tier2 run root.",
    ]
    readme.write_text("\n".join(lines) + "\n")

    write_latex_shim(out_dir / "latex_include")
    print(f"Paper artifacts written to: {out_dir}")


if __name__ == "__main__":
    main()
