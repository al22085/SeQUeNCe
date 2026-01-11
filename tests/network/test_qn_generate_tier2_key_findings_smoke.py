import csv
import subprocess
from pathlib import Path


def test_generate_tier2_key_findings_smoke(tmp_path: Path):
    root = tmp_path / "run"
    root.mkdir(parents=True, exist_ok=True)
    plots_dir = root / "plots_linearity"
    plots_dir.mkdir(parents=True, exist_ok=True)

    summary_path = root / "line_vs_curve_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
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
            ]
        )
        writer.writerow(["policy", "", "global_rank", "", "3", "0.67", "0.9", "0.02", "0.05", "1.1", "1.2"])

    analysis_dir = root / "analysis_path_coverage"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    cov_summary = analysis_dir / "path_coverage_thresholds_summary.csv"
    with cov_summary.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["scope", "upgrade_policy", "label", "n_pairs", "coverage_threshold_k_median", "k_star_median"])
        writer.writerow(["policy", "global_rank", "", "3", "5", "9"])

    topo_dir = root / "TOY"
    topo_dir.mkdir(parents=True, exist_ok=True)
    pairs_csv = topo_dir / "pairs_repr3.csv"
    with pairs_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "topology_id",
                "label",
                "target_km",
                "found",
                "src_node",
                "dst_node",
                "dist_km",
                "abs_error_km",
                "rel_error",
            ]
        )
        writer.writerow(["TOY", "short_1", "404", "false", "", "", "", "", ""])

    out_md = plots_dir / "tier2_key_findings.md"
    subprocess.run(
        [
            "python",
            "scripts/qn_generate_tier2_key_findings.py",
            "--root-dir",
            str(root),
            "--analysis-dir",
            str(analysis_dir),
            "--out-path",
            str(out_md),
        ],
        check=True,
    )
    assert out_md.exists()
