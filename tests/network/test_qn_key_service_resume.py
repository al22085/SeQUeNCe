import json
import subprocess
import tempfile
from pathlib import Path


def test_key_service_resume_equivalence():
    with tempfile.TemporaryDirectory() as tmpdir:
        full_out = Path(tmpdir) / "full"
        split_out = Path(tmpdir) / "split"

        base_cmd = [
            "python",
            "scripts/qn_key_service_availability.py",
            "--preset",
            "preset_key_service_otp_smoke",
            "--out-dir",
            str(full_out),
        ]
        # full run
        subprocess.run(base_cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        full_summary = json.loads((full_out / "summary.json").read_text())

        # split run: horizon half then resume
        half_cmd = base_cmd.copy()
        half_cmd[-1] = str(split_out)
        half_cmd += ["--horizon-s", "0.25"]
        subprocess.run(half_cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        resume_cmd = base_cmd.copy()
        resume_cmd[-1] = str(split_out)
        subprocess.run(resume_cmd + ["--resume"], check=True, cwd=Path(__file__).resolve().parents[2])
        split_summary = json.loads((split_out / "summary.json").read_text())

        assert full_summary["availability"] == split_summary["availability"]
