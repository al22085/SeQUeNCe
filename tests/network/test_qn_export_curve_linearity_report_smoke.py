import csv
import subprocess
import tempfile
from pathlib import Path


def test_export_curve_linearity_report_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        topo_dir = root / "TOP_X"
        policy_dir = topo_dir / "global_rank"
        policy_dir.mkdir(parents=True, exist_ok=True)

        curve_points = policy_dir / "curve_points.csv"
        with curve_points.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "topology_id",
                    "upgrade_policy",
                    "pair",
                    "label",
                    "target_km",
                    "dist_km",
                    "abs_error_km",
                    "rel_error",
                    "upgrade_k",
                    "upgraded_fraction",
                    "bk0",
                    "eqt_frontier",
                    "ratio_vs_bk0",
                ]
            )
            w.writerow(["TOP_X", "global_rank", "A-B", "short_1", "404", "400", "4", "0.01", "0", "0.0", "1", "1", "1.0"])
            w.writerow(["TOP_X", "global_rank", "A-B", "short_1", "404", "400", "4", "0.01", "1", "0.5", "1", "1.1", "1.1"])

        curve_metrics = policy_dir / "curve_metrics.csv"
        with curve_metrics.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "topology_id",
                    "upgrade_policy",
                    "pair",
                    "label",
                    "target_km",
                    "dist_km",
                    "abs_error_km",
                    "rel_error",
                    "kmax",
                    "r2",
                    "curvature",
                    "classification",
                    "ratio_k21",
                    "clipped",
                ]
            )
            w.writerow(["TOP_X", "global_rank", "A-B", "short_1", "404", "400", "4", "0.01", "1", "0.99", "0.01", "approximately_linear", "1.1", "False"])

        cmd = [
            "python",
            "scripts/qn_export_curve_linearity_report.py",
            "--root-dir",
            str(root),
            "--workers",
            "2",
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])

        assert (root / "line_vs_curve_summary.csv").exists()
        assert (root / "k_star_table.csv").exists()
        assert (root / "line_vs_curve_report.md").exists()

