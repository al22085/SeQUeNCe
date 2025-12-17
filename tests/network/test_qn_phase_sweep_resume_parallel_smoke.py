import csv
import os
import subprocess
import tempfile
from pathlib import Path


def test_phase_sweep_resume_parallel():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "phase"
        cmd = [
            "python",
            "scripts/qn_phase_sweep.py",
            "--strategies",
            "BK",
            "--distances",
            "1000",
            "--etas",
            "0.4,0.6",
            "--seeds",
            "0,1",
            "--num-trials",
            "1",
            "--deadline-mode",
            "scaled",
            "--deadline-factor",
            "1000",
            "--setup-factor",
            "500",
            "--min-start-delay-s",
            "0.001",
            "--mem-coh-s",
            "0.005",
            "--attn",
            "0.005",
            "--optical-eta",
            "0.4",
            "--fidelity",
            "0.5",
            "--workers",
            "1",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        raw_path = out_dir / "phase_raw.csv"
        assert raw_path.exists()
        with raw_path.open() as f:
            rows1 = list(csv.reader(f))

        # resume should not add duplicates
        cmd.append("--resume")
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        with raw_path.open() as f:
            rows2 = list(csv.reader(f))
        assert len(rows1) == len(rows2)

        agg_path = out_dir / "phase_agg.csv"
        assert agg_path.exists()
