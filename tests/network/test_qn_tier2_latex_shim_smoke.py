import json
import subprocess
import sys
from pathlib import Path


def write_csv(path: Path, header: str, row: str) -> None:
    path.write_text(f"{header}\n{row}\n")


def test_latex_shim_smoke(tmp_path: Path) -> None:
    root = tmp_path / "tier2_run"
    plots = root / "plots_linearity"
    coverage = root / "analysis_path_coverage"
    coverage_plots = coverage / "plots_path_coverage"
    plots.mkdir(parents=True)
    coverage_plots.mkdir(parents=True)

    write_csv(
        root / "summary_upgrade_curves.csv",
        "topology_id,policy,metric,missing_pairs_total,missing_pairs_by_label",
        "TOPO,global_rank,median,0,{}",
    )
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
    parallel_report = {
        "requested_workers": 20,
        "verify_info": {"active_workers": 20, "aggregate_cpu": 2000.0, "expected_cpu": 2000.0},
        "verify_mode": "pid_activity_strict",
    }
    (root / "parallel_report.json").write_text(json.dumps(parallel_report))

    subprocess.run(
        [sys.executable, "scripts/qn_export_tier2_paper_artifacts.py", "--root-dir", str(root)],
        check=True,
    )

    bundle = root / "paper_artifacts_bundle.zip"
    subprocess.run(
        [
            sys.executable,
            "scripts/qn_bundle_tier2_paper_artifacts.py",
            "--root-dir",
            str(root),
            "--bundle-path",
            str(bundle),
        ],
        check=True,
    )

    out_dir = tmp_path / "extracted"
    subprocess.run(
        [
            sys.executable,
            "scripts/qn_unpack_tier2_paper_bundle.py",
            "--bundle",
            str(bundle),
            "--out-dir",
            str(out_dir),
            "--overwrite",
        ],
        check=True,
    )

    shim = out_dir / "paper_artifacts" / "latex_include" / "tier2_paper_artifacts.tex"
    assert shim.exists()
    text = shim.read_text()
    assert "TierTwoLinearityTable" in text
    assert "figs/fig_linearity_overview.png" in text

    figs = out_dir / "paper_artifacts" / "figs"
    tables = out_dir / "paper_artifacts" / "tables"
    assert (figs / "fig_linearity_overview.png").exists()
    assert (tables / "table_linearity_summary.tex").exists()
