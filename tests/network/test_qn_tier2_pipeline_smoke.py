import csv
import subprocess
import tempfile
from pathlib import Path


def test_tier2_pipeline_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        edge_csv = base / "toy.csv"
        with edge_csv.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["u", "v", "linkLengthInKm"])
            writer.writerow(["A", "B", 10])
            writer.writerow(["B", "C", 10])
            writer.writerow(["A", "C", 25])

        out_dir = base / "run"
        cmd = [
            "python",
            "scripts/qn_run_topology_policy_upgrade_curves.py",
            "--edge-csv-list",
            str(edge_csv),
            "--topology-id-list",
            "toy",
            "--upgrade-policies",
            "global_rank",
            "--upgrade-k-mode",
            "explicit",
            "--upgrade-k-list",
            "0,1",
            "--eta",
            "0.9",
            "--target",
            "0.99",
            "--kbits",
            "1.0",
            "--seeds",
            "0",
            "--targets-km",
            "10",
            "--pairs-per-target",
            "1",
            "--pair-distance-rel-tol",
            "0.5",
            "--no-binary-search",
            "--load-min",
            "0.01",
            "--load-max",
            "0.02",
            "--load-tol",
            "0.01",
            "--horizon-s",
            "0.05",
            "--tau-s",
            "0.02",
            "--attempt-rate-opt-hz",
            "5000",
            "--attempt-rate-sc-hz",
            "10000",
            "--coherence-opt-s",
            "0.05",
            "--coherence-sc-s",
            "0.1",
            "--loss-db-per-km",
            "0.2",
            "--segment-length-km",
            "50",
            "--allow-thread-fallback",
            "--no-verify-parallel",
            "--utilization-monitor-samples",
            "0",
            "--workers",
            "2",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])

        subprocess.run(
            [
                "python",
                "scripts/qn_export_curve_linearity_report.py",
                "--root-dir",
                str(out_dir),
                "--workers",
                "2",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        subprocess.run(
            [
                "python",
                "scripts/plot_qn_curve_linearity_report.py",
                "--root-dir",
                str(out_dir),
                "--workers",
                "2",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        subprocess.run(
            [
                "python",
                "scripts/qn_analyze_path_coverage_across_topologies.py",
                "--root-dir",
                str(out_dir),
                "--distances-dir",
                str(base),
                "--out-dir",
                str(out_dir / "analysis_path_coverage"),
                "--workers",
                "2",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        subprocess.run(
            [
                "python",
                "scripts/plot_qn_path_coverage_mechanism.py",
                "--analysis-dir",
                str(out_dir / "analysis_path_coverage"),
                "--workers",
                "2",
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        subprocess.run(
            [
                "python",
                "scripts/qn_generate_paper_key_findings.py",
                "--root-dir",
                str(out_dir),
                "--analysis-dir",
                str(out_dir / "analysis_path_coverage"),
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )

        assert (out_dir / "plots_linearity" / "paper_key_findings.md").exists()
