import json
import subprocess
import tempfile
from pathlib import Path


def test_entanglement_service_smoke_chain():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "ent"
        cmd = [
            "python",
            "scripts/qn_entanglement_service_availability.py",
            "--strategy",
            "BK",
            "--topology",
            "chain",
            "--num-requests",
            "10",
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
        summary = json.loads((out_dir / "summary.json").read_text())
        assert 0.0 <= summary["availability_mean"] <= 1.0
