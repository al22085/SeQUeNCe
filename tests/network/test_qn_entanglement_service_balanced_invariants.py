import csv
import subprocess
import tempfile
from pathlib import Path


def test_balanced_invariants_swap_attempts_present():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_csv = Path(tmpdir) / "bal_inv.csv"
        cmd = [
            "python",
            "scripts/qn_entanglement_service_calibrate_pair.py",
            "--src",
            "1",
            "--dst",
            "4",
            "--etas",
            "0.9",
            "--loads",
            "0.05",
            "--seeds",
            "0,1",
            "--horizon-s",
            "0.3",
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
        with out_csv.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert rows, "Expected calibration rows"
        for row in rows:
            delivered_pairs = float(row["delivered_pairs"])
            eg_success_events = float(row["eg_success_events"])
            swap_attempts = float(row["swap_attempts"])
            swap_success = float(row["swap_success"])
            # Balanced schedule on a multi-segment path must perform swaps to deliver.
            assert delivered_pairs > 0
            assert swap_attempts > 0
            assert swap_success > 0
            # Delivering one end-to-end pair should require multiple segment successes.
            assert delivered_pairs * 2 <= eg_success_events
