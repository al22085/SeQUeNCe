import subprocess
from pathlib import Path


def test_stop_running_jobs_noop():
    cmd = [
        "python",
        "scripts/qn_stop_running_jobs.py",
        "--pattern",
        "__no_match__",
        "--no-defaults",
    ]
    subprocess.run(cmd, check=True, cwd=Path(__file__).resolve().parents[2])
