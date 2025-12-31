import csv
import subprocess
import tempfile
from pathlib import Path


def test_topology_policy_sensitivity_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        edge_csv = base / "toy_edges.csv"
        pair_csv = base / "toy_pairs.csv"
        out_dir = base / "out"

        # tiny 3-node triangle
        with edge_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["u", "v", "distance_km"])
            w.writerow(["A", "B", "10"])
            w.writerow(["B", "C", "10"])
            w.writerow(["A", "C", "25"])

        with pair_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["src", "dst", "distance_km"])
            w.writerow(["A", "C", "20"])

        cmd = [
            "python",
            "scripts/qn_run_topology_and_policy_sensitivity.py",
            "--edge-csv-list",
            str(edge_csv),
            "--pairs-csv-list",
            str(pair_csv),
            "--topology-id-list",
            "toy",
            "--upgrade-policies",
            "pair_path_only",
            "--upgrade-k-list",
            "0,1",
            "--targets",
            "0.99",
            "--etas",
            "0.9",
            "--kbits-list",
            "1.0",
            "--seeds",
            "0",
            "--load-min",
            "0.01",
            "--load-max",
            "0.05",
            "--load-tol",
            "0.02",
            "--horizon-s",
            "0.1",
            "--tau-s",
            "0.05",
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
            "--workers",
            "2",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        combined = out_dir / "combined_upgrade_policy_curves.csv"
        assert combined.exists()
