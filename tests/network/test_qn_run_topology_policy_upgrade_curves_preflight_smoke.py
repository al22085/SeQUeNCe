import csv
import subprocess
import tempfile
from pathlib import Path


def test_run_topology_policy_upgrade_curves_preflight_smoke():
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
            "--preflight",
            "--no-preflight-strict",
            "--verify-parallel-mode",
            "pid_only",
            "--preflight-task-seconds",
            "0.2",
            "--preflight-num-tasks",
            "4",
            "--edge-csv-list",
            str(edge_csv),
            "--topology-id-list",
            "toy",
            "--upgrade-policies",
            "global_rank",
            "--upgrade-k-list",
            "0",
            "--upgrade-k-mode",
            "explicit",
            "--allow-thread-fallback",
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
            "--load-min",
            "0.01",
            "--load-max",
            "0.01",
            "--load-tol",
            "0.01",
            "--no-binary-search",
            "--horizon-s",
            "0.02",
            "--tau-s",
            "0.01",
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
        assert (out_dir / "parallel_report.json").exists()
