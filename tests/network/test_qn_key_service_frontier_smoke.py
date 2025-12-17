import csv
import subprocess
import tempfile
from pathlib import Path


def test_key_service_frontier_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "frontier"
        cmd = [
            "python",
            "scripts/qn_key_service_migration_frontier.py",
            "--strategies",
            "BK",
            "--lambdas",
            "0.5",
            "--kmax-list",
            "1e4",
            "--otp-rate-min-bps",
            "1e3",
            "--otp-rate-max-bps",
            "2e3",
            "--rate-steps",
            "3",
            "--binary-search",
            "--workers",
            "1",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        agg = out_dir / "frontier_agg.csv"
        assert agg.exists()
        with agg.open() as f:
            rows = list(csv.DictReader(f))
            assert rows
