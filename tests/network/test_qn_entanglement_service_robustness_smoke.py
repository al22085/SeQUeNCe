import csv
import subprocess
import tempfile
from pathlib import Path


def test_entanglement_service_robustness_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        out_dir = base / "robust"
        subprocess.run(
            [
                "python",
                "scripts/qn_entanglement_service_robustness_frontier.py",
                "--pairs",
                "1-2",
                "--etas",
                "0.9",
                "--upgrade-k-list",
                "0,21",
                "--strategies",
                "BK,EQT",
                "--targets",
                "0.9",
                "--kbits-list",
                "1.0",
                "--seeds",
                "0",
                "--load-grid",
                "0.5,1.0",
                "--horizon-s",
                "0.2",
                "--tau-s",
                "0.05",
                "--attempt-rate-opt-hz",
                "10000",
                "--attempt-rate-sc-hz",
                "20000",
                "--coherence-opt-s",
                "0.05",
                "--coherence-sc-s",
                "0.05",
                "--segment-length-km",
                "50",
                "--edge-distance-csv",
                "data/nsfnet_distances_topologybench.csv",
                "--allow-thread-fallback",
                "--no-verify-parallel",
                "--workers",
                "2",
                "--out-dir",
                str(out_dir),
            ],
            check=True,
            cwd=Path(__file__).resolve().parents[2],
        )
        pair_frontier = out_dir / "robust_frontier_pairs.csv"
        agg = out_dir / "robust_frontier_agg.csv"
        assert pair_frontier.exists()
        assert agg.exists()
        with agg.open() as f:
            rows = list(csv.DictReader(f))
            assert rows
            # ensure at least BK row present
            assert any(r["strategy"] == "BK" for r in rows)
