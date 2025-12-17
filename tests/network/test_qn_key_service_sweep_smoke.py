import csv
import subprocess
import tempfile
from pathlib import Path


def test_key_service_sweep_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "sweep"
        cmd = [
            "python",
            "scripts/qn_key_service_sweep.py",
            "--strategies",
            "BK,EQT",
            "--lambdas",
            "0.5,1.0",
            "--kmax-list",
            "1e4",
            "--seeds",
            "0,1",
            "--horizon-s",
            "0.2",
            "--tau-s",
            "0.05",
            "--workers",
            "1",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        agg = out_dir / "key_service_sweep_agg.csv"
        assert agg.exists()
        with agg.open() as f:
            rows = list(csv.DictReader(f))
            assert rows
            for r in rows:
                a = float(r["availability_mean"])
                assert 0.0 <= a <= 1.0
