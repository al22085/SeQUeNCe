import csv
import subprocess
import tempfile
from pathlib import Path


def test_entanglement_service_frontier_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "frontier"
        cmd = [
            "python",
            "scripts/qn_entanglement_service_frontier.py",
            "--strategies",
            "BK",
            "--targets",
            "0.9,0.99",
            "--kbits-list",
            "0.5",
            "--load-min",
            "0.1",
            "--load-max",
            "1.0",
            "--load-tol",
            "0.2",
            "--seeds",
            "0",
            "--num-requests",
            "6",
            "--horizon-s",
            "0.05",
            "--tau-s",
            "0.02",
            "--workers",
            "1",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        agg = out_dir / "ent_frontier_agg.csv"
        assert agg.exists()
        with agg.open() as f:
            rows = list(csv.DictReader(f))
            assert rows
            by_target = {}
            for r in rows:
                by_target.setdefault(float(r["target"]), float(r["frontier_load"]))
            assert by_target[0.99] <= by_target[0.9] + 1e-6
