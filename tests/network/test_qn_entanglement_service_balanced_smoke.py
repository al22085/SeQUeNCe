import json
import subprocess
import tempfile
from pathlib import Path


def test_balanced_schedule_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_csv = Path(tmpdir) / "bal.csv"
        cmd = [
            "python",
            "scripts/qn_entanglement_service_calibrate_pair.py",
            "--src",
            "1",
            "--dst",
            "2",
            "--etas",
            "0.9",
            "--loads",
            "0.1",
            "--seeds",
            "0,1",
            "--horizon-s",
            "0.2",
            "--tau-s",
            "0.1",
            "--attempt-rate-opt-hz",
            "10000",
            "--attempt-rate-sc-hz",
            "20000",
            "--coherence-opt-s",
            "0.05",
            "--coherence-sc-s",
            "0.1",
            "--loss-db-per-km",
            "0.2",
            "--segment-length-km",
            "50",
            "--edge-distance-csv",
            "data/nsfnet_distances_topologybench.csv",
            "--distance-dataset-id",
            "topologybench_nsfnet13",
            "--otp-data-rate-bps",
            "1",
            "--otp-session-duration-s",
            "0.01",
            "--otp-directions",
            "1",
            "--key-bits-per-pair",
            "1",
            "--workers",
            "2",
            "--network-scope",
            "shortest_path",
            "--swap-schedule",
            "balanced",
            "--debug-stats",
            "--out-csv",
            str(out_csv),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        text = out_csv.read_text()
        assert ",0.0,0.0,0," not in text  # expect some delivered bits
