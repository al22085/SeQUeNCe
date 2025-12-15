import json
import sys
from pathlib import Path


def test_network_availability_smoke():
    root = Path(__file__).resolve().parents[2]
    script = root / "scripts" / "qn_network_availability.py"
    out = Path("/tmp/qn_net_avail_smoke.json")

    cmd = [
        sys.executable,
        str(script),
        "--arch",
        "optical",
        "--strategy",
        "BK",
        "--distance",
        "1e3",
        "--deadline",
        "10",
        "--num-trials",
        "10",
        "--seed",
        "1",
        "--format",
        "json",
        "--out",
        str(out),
    ]
    assert out.parent.exists()
    import subprocess

    subprocess.check_call(cmd)
    data = json.loads(out.read_text())
    assert 0.0 <= data["availability_req"] <= 1.0
    assert data["satisfied"] <= data["num_trials"]
