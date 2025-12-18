import json
import subprocess
import tempfile
from pathlib import Path


def test_entanglement_service_determinism():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir1 = Path(tmpdir) / "ent1"
        out_dir2 = Path(tmpdir) / "ent2"
        base_cmd = [
            "python",
            "scripts/qn_entanglement_service_availability.py",
            "--strategy",
            "BK",
            "--topology",
            "chain",
            "--num-requests",
            "8",
            "--horizon-s",
            "0.05",
            "--tau-s",
            "0.02",
            "--seed",
            "42",
            "--workers",
            "1",
        ]
        subprocess.run(base_cmd + ["--out-dir", str(out_dir1)], check=True, cwd=Path(__file__).resolve().parents[2])
        subprocess.run(base_cmd + ["--out-dir", str(out_dir2)], check=True, cwd=Path(__file__).resolve().parents[2])
        s1 = json.loads((out_dir1 / "summary.json").read_text())
        s2 = json.loads((out_dir2 / "summary.json").read_text())
        assert s1["availability_mean"] == s2["availability_mean"]
