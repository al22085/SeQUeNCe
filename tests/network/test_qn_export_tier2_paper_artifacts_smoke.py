import json
import subprocess
import sys
from pathlib import Path


def write_csv(path: Path, header: str, row: str) -> None:
    path.write_text(f"{header}\n{row}\n")


def test_export_tier2_paper_artifacts_smoke(tmp_path: Path) -> None:
    root = tmp_path / "tier2_run"
    plots = root / "plots_linearity"
    coverage = root / "analysis_path_coverage"
    coverage_plots = coverage / "plots_path_coverage"
    plots.mkdir(parents=True)
    coverage_plots.mkdir(parents=True)

    write_csv(
        root / "line_vs_curve_summary.csv",
        "scope,upgrade_policy,fraction_nonlinear,median_r2,median_curvature",
        "policy,global_rank,0.5,0.9,0.01",
    )
    write_csv(
        coverage / "path_coverage_thresholds_summary.csv",
        "scope,upgrade_policy,coverage_threshold_k_median,k_star_median",
        "policy,global_rank,2.0,0.5",
    )
    write_csv(
        root / "summary_upgrade_curves.csv",
        "topology_id,policy,metric,eta,target_A,kbits,missing_pairs_total,missing_pairs_by_label",
        "TOPO,global_rank,median,0.9,0.99,1.0,0,{}",
    )
    (plots / "paper_key_findings.md").write_text("# ok\n")
    (plots / "fraction_nonlinear_by_policy.png").write_bytes(b"\x89PNG\r\n")
    (coverage_plots / "ratio_vs_path_upgraded_fraction.png").write_bytes(b"\x89PNG\r\n")

    chosen = {
        "chosen_tolerance": 0.15,
        "targets_km": [404.0, 511.0, 1002.0],
        "pairs_per_target": 2,
        "chosen_topologies": ["TOPO"],
    }
    (root / "chosen_tolerance.json").write_text(json.dumps(chosen))

    cmd = [
        sys.executable,
        "scripts/qn_export_tier2_paper_artifacts.py",
        "--root-dir",
        str(root),
    ]
    subprocess.run(cmd, check=True)
    out_dir = root / "paper_artifacts"
    assert (out_dir / "README.md").exists()
    assert (out_dir / "tables" / "table_linearity_summary.tex").exists()
    assert (out_dir / "tables" / "table_coverage_thresholds.tex").exists()
    assert (out_dir / "tables" / "table_run_metadata.tex").exists()
    assert (out_dir / "figures" / "fig_linearity_overview.png").exists()
    assert (out_dir / "figures" / "fig_path_coverage_overview.png").exists()
