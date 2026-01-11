import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest

from sequence.qn.parallel import verify_parallelism


def test_verify_parallelism_spawns_workers():
    try:
        info = verify_parallelism(2, task_seconds=0.1, mode="pid_only")
    except RuntimeError as exc:
        pytest.skip(f"ProcessPool unavailable in this environment: {exc}")
    assert info["effective_workers"] == 2
    assert len(info["worker_pids"]) >= 2
    assert "cpu_limit_info" in info
