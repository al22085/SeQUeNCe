import json
import sys
from pathlib import Path
import subprocess


def test_qn_e2e_proof_minimal_ideal_nonzero():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "qn_e2e_proof_minimal.py"
    out = Path("/tmp/qn_e2e_proof_minimal.json")
    cmd = [
        sys.executable,
        str(script),
        "--sanity",
        "ideal",
        "--strategy",
        "BK",
        "--seed",
        "0",
        "--num-trials",
        "20",
        "--deadline-s",
        "0.1",
        "--min-start-delay-s",
        "0.01",
        "--setup-factor",
        "5000",
        "--format",
        "json",
    ]
    with out.open("w") as f:
        subprocess.check_call(cmd, stdout=f)
    data = json.loads(out.read_text())
    assert data["availability_req"] > 0.0
