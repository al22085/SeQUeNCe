import csv
import subprocess
import tempfile
from pathlib import Path


def test_run_topology_policy_upgrade_curves_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        edge_csv = base / "toy_edges.csv"
        out_dir = base / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        with edge_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["u", "v", "linkLengthInKm"])
            w.writerow(["A", "B", "10"])
            w.writerow(["B", "C", "10"])
            w.writerow(["A", "C", "25"])

        cmd = [
            "python",
            "scripts/qn_run_topology_policy_upgrade_curves.py",
            "--edge-csv-list",
            str(edge_csv),
            "--topology-id-list",
            "toy",
            "--upgrade-policies",
            "global_rank",
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
            "--load-min",
            "0.01",
            "--load-max",
            "0.05",
            "--load-tol",
            "0.02",
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
            "--workers",
            "2",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])

        summary = out_dir / "summary_upgrade_curves.csv"
        assert summary.exists()
        with summary.open() as f:
            rows = list(csv.DictReader(f))
        assert rows
        assert {"topology_id", "policy", "metric", "ratio_k21"}.issubset(rows[0].keys())
