import csv
import subprocess
import tempfile
from pathlib import Path


def test_policy_comparison_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        edge_csv = base / "edges.csv"
        pairs_csv = base / "pairs.csv"
        out_dir = base / "out"
        out_dir.mkdir(parents=True, exist_ok=True)

        with edge_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["u", "v", "distance_km"])
            w.writerow(["A", "B", "10"])
            w.writerow(["B", "C", "10"])
            w.writerow(["A", "C", "25"])

        with pairs_csv.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["src", "dst", "distance_km"])
            w.writerow(["A", "C", "20"])

        cmd = [
            "python",
            "scripts/qn_run_policy_comparison.py",
            "--edge-distance-csv",
            str(edge_csv),
            "--topology-id",
            "toy",
            "--pairs-csv",
            str(pairs_csv),
            "--upgrade-policies",
            "pair_path_only",
            "--upgrade-k-list",
            "0,1",
            "--target",
            "0.99",
            "--eta",
            "0.9",
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
        agg = out_dir / "policy_comparison_agg.csv"
        assert agg.exists()
        with agg.open() as f:
            rows = list(csv.DictReader(f))
        assert rows
