import json
import subprocess
import sys
from pathlib import Path


def test_qn_network_availability_sequence_smoke():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "qn_network_availability_sequence.py"
    out = Path("/tmp/qn_net_avail_seq_smoke.json")
    cmd = [
        sys.executable,
        str(script),
        "--strategy",
        "BK",
        "--distance",
        "1e3",
        "--deadline",
        "2e4",
        "--num-trials",
        "5",
        "--seed",
        "1",
        "--format",
        "json",
        "--out",
        str(out),
    ]
    subprocess.check_call(cmd)
    data = json.loads(out.read_text())
    assert 0.0 <= data["availability_req"] <= 1.0
    assert data["satisfied"] <= data["num_trials"]
