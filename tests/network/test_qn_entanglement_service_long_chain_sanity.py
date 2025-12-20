import subprocess
import tempfile
from pathlib import Path


def test_long_chain_sanity():
    # Synthetic chain with zero loss, high p_eg should deliver pairs
    with tempfile.TemporaryDirectory() as tmpdir:
        out_csv = Path(tmpdir) / "sanity.csv"
        cmd = [
            "python",
            "scripts/qn_entanglement_service_calibrate_pair.py",
            "--src",
            "1",
            "--dst",
            "2",
            "--etas",
            "1.0",
            "--loads",
            "0.5",
            "--seeds",
            "0,1",
            "--horizon-s",
            "0.2",
            "--tau-s",
            "0.1",
            "--attempt-rate-opt-hz",
            "10000",
            "--attempt-rate-sc-hz",
            "10000",
            "--coherence-opt-s",
            "1.0",
            "--coherence-sc-s",
            "1.0",
            "--loss-db-per-km",
            "0.0",
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
            "--out-csv",
            str(out_csv),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        text = out_csv.read_text()
        # Should deliver at least some bits (non-zero)
        assert ",0.0,0.0,0," not in text  # crude check that bits_delivered not zero for all rows
