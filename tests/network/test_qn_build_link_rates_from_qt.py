import json
import subprocess
import tempfile
from pathlib import Path


def test_build_link_rates_from_qt_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        qt_csv = tmp / "qt.csv"
        qt_csv.write_text("strategy,u,v,success_prob\nBK,1,2,0.5\nBK,2,3,0.7\n")
        out_json = tmp / "rates.json"
        cmd = [
            "python",
            "scripts/qn_build_link_rates_from_qt.py",
            "--in",
            str(qt_csv),
            "--prob-column",
            "success_prob",
            "--edge-u-column",
            "u",
            "--edge-v-column",
            "v",
            "--attempt-rate-hz",
            "100",
            "--key-bits-per-success",
            "2",
            "--out-json",
            str(out_json),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        data = json.loads(out_json.read_text())
        # Edge 1-2 prob 0.5 -> rate 100*0.5*2=100; Edge 2-3 prob 0.7 -> 140
        assert data
        assert abs(data["1-2"] - 100.0) < 1e-6
        assert abs(data["2-3"] - 140.0) < 1e-6
