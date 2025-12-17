import subprocess
import tempfile
from pathlib import Path


def test_presets_and_cli_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir) / "phase"
        cmd = [
            "python",
            "scripts/qn_phase_sweep.py",
            "--preset",
            "preset_non_saturated_smoke",
            "--workers",
            "1",
            "--strategies",
            "BK",
            "--distances",
            "1000",
            "--etas",
            "0.6",
            "--seeds",
            "0",
            "--num-trials",
            "1",
            "--out-dir",
            str(out_dir),
        ]
        subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
        assert (out_dir / "phase_raw.csv").exists()
        assert (out_dir / "phase_agg.csv").exists()
