import json
import subprocess
import tempfile
from pathlib import Path


def test_key_service_determinism():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "ks"
        base_cmd = [
            "python",
            "scripts/qn_key_service_availability.py",
            "--preset",
            "preset_key_service_otp_smoke",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(base_cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        summary1 = json.loads((out_dir / "summary.json").read_text())
        raw1 = (out_dir / "requests_raw.csv").read_text()

        # second run to compare
        out_dir2 = Path(tmpdir) / "ks2"
        base_cmd[-1] = str(out_dir2)
        subprocess.run(base_cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        summary2 = json.loads((out_dir2 / "summary.json").read_text())
        raw2 = (out_dir2 / "requests_raw.csv").read_text()

        assert summary1["availability"] == summary2["availability"]
        assert raw1.splitlines()[:5] == raw2.splitlines()[:5]
