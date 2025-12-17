import json
import subprocess
import tempfile
from pathlib import Path


def test_key_service_smoke_outputs():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "ks"
        cmd = [
            "python",
            "scripts/qn_key_service_availability.py",
            "--preset",
            "preset_key_service_otp_smoke",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        raw = out_dir / "requests_raw.csv"
        summary = out_dir / "summary.json"
        assert raw.exists()
        assert summary.exists()
        data = json.loads(summary.read_text())
        assert 0.0 <= data["availability"] <= 1.0
