import csv
import subprocess
import tempfile
from pathlib import Path


def test_key_service_monotonic_lambda():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "sweep"
        cmd = [
            "python",
            "scripts/qn_key_service_sweep.py",
            "--strategies",
            "BK",
            "--lambdas",
            "0.5,1.5",
            "--kmax-list",
            "1e4",
            "--seeds",
            "0",
            "--horizon-s",
            "0.3",
            "--tau-s",
            "0.05",
            "--workers",
            "1",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        agg = out_dir / "key_service_sweep_agg.csv"
        with agg.open() as f:
            rows = list(csv.DictReader(f))
        # Extract by lambda
        avail = {}
        for r in rows:
            if r["strategy"] == "BK":
                avail[float(r["lambda"])] = float(r["availability_mean"])
        assert len(avail) == 2
        assert avail[1.5] <= avail[0.5]
