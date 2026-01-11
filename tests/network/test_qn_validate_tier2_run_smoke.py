import json
import subprocess
import sys
from pathlib import Path


def write_csv(path: Path, header: str, row: str) -> None:
    path.write_text(f"{header}\n{row}\n")


def test_validate_tier2_run_smoke(tmp_path: Path) -> None:
    root = tmp_path / "tier2_run"
    (root / "analysis_path_coverage").mkdir(parents=True)
    (root / "plots_linearity").mkdir(parents=True)

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
        root / "analysis_path_coverage" / "path_coverage_thresholds_summary.csv",
        "scope,upgrade_policy,coverage_threshold_k_median,k_star_median",
        "policy,global_rank,2.0,0.5",
    )
    (root / "plots_linearity" / "paper_key_findings.md").write_text("# ok\n")
    parallel_report = {
        "requested_workers": 20,
        "verify_info": {"active_workers": 20, "aggregate_cpu": 2000.0, "expected_cpu": 2000.0},
        "verify_mode": "pid_activity_strict",
    }
    (root / "parallel_report.json").write_text(json.dumps(parallel_report))

    cmd = [
        sys.executable,
        "scripts/qn_validate_tier2_run.py",
        "--root-dir",
        str(root),
    ]
    subprocess.run(cmd, check=True)
    report = root / "paper_artifacts" / "validation_report.json"
    assert report.exists()


def test_validate_tier2_run_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "tier2_run"
    root.mkdir()
    cmd = [
        sys.executable,
        "scripts/qn_validate_tier2_run.py",
        "--root-dir",
        str(root),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode != 0
    assert "Missing required files" in result.stderr + result.stdout
