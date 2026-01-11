import csv
import json
import subprocess
import tempfile
from pathlib import Path


def test_analyze_path_coverage_across_topologies_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        topo_id = "TOPO_Y"
        topo_dir = root / topo_id / "global_rank"
        topo_dir.mkdir(parents=True, exist_ok=True)

        # topology selection
        selection = {
            "selected_topologies": [topo_id],
        }
        (root / "topology_selection.json").write_text(json.dumps(selection), encoding="utf-8")

        # pairs CSV
        pairs_csv = root / topo_id / "pairs_repr3.csv"
        pairs_csv.parent.mkdir(parents=True, exist_ok=True)
        with pairs_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["label", "src_node", "dst_node", "dist_km", "target_km", "abs_error_km", "rel_error"])
            w.writerow(["short_1", "A", "C", "20", "404", "384", "0.95"])

        # curve points for a single policy
        curve_points = topo_dir / "curve_points.csv"
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
            w.writerow([topo_id, "global_rank", "A-C", "short_1", "404", "20", "384", "0.95", "0", "0.0", "1", "1", "1.0"])
            w.writerow([topo_id, "global_rank", "A-C", "short_1", "404", "20", "384", "0.95", "1", "0.5", "1", "1.1", "1.1"])

        # distances CSV
        dist_dir = root / "distances"
        dist_dir.mkdir(parents=True, exist_ok=True)
        dist_csv = dist_dir / f"{topo_id}.csv"
        with dist_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["u", "v", "distance_km"])
            w.writerow(["A", "B", "10"])
            w.writerow(["B", "C", "10"])

        cmd = [
            "python",
            "scripts/qn_analyze_path_coverage_across_topologies.py",
            "--root-dir",
            str(root),
            "--distances-dir",
            str(dist_dir),
            "--upgrade-policies",
            "global_rank",
            "--segment-length-km",
            "50",
            "--workers",
            "2",
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])

        assert (root / "path_coverage_join.csv").exists()
        assert (root / "path_coverage_thresholds.csv").exists()

