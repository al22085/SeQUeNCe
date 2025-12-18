import json
import subprocess
import tempfile
from pathlib import Path


def test_build_link_rates_from_qt_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        qt_csv = tmp / "qt.csv"
        qt_csv.write_text("strategy,success_prob\nBK,0.5\nBK,0.7\n")
        out_json = tmp / "rates.json"
        cmd = [
            "python",
            "scripts/qn_build_link_rates_from_qt.py",
            "--in",
            str(qt_csv),
            "--prob-column",
            "success_prob",
            "--attempt-rate-hz",
            "100",
            "--key-bits-per-success",
            "2",
            "--out-json",
            str(out_json),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        data = json.loads(out_json.read_text())
        # Mean prob = 0.6 -> rate = 100 * 0.6 * 2 = 120
        assert data
        # Ensure at least one edge present with expected rate
        rate_values = list(data.values())
        assert abs(rate_values[0] - 120.0) < 1e-6
