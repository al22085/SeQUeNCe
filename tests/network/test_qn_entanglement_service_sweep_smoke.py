import csv
import subprocess
import tempfile
from pathlib import Path


def test_entanglement_service_sweep_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "sweep"
        cmd = [
            "python",
            "scripts/qn_entanglement_service_sweep.py",
            "--strategies",
            "BK",
            "--loads",
            "0.5,1.0",
            "--seeds",
            "0",
            "--num-requests",
            "6",
            "--horizon-s",
            "0.05",
            "--tau-s",
            "0.02",
            "--workers",
            "2",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        agg = out_dir / "ent_sweep_agg.csv"
        assert agg.exists()
        with agg.open() as f:
            rows = list(csv.DictReader(f))
            assert rows
