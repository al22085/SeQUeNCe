import json
import subprocess
import tempfile
from pathlib import Path


def test_entanglement_service_kbits_dual_outputs():
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
            "6",
            "--horizon-s",
            "0.05",
            "--tau-s",
            "0.02",
            "--key-bits-per-pair-list",
            "0.5,1.0",
            "--workers",
            "2",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        for kb in ["0.5", "1.0"]:
            summary_path = out_dir / f"kbits_{kb}" / "summary.json"
            assert summary_path.exists()
            data = json.loads(summary_path.read_text())
            assert data["key_bits_per_pair"] == float(kb)
