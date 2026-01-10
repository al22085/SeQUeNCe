"""Parallelism helpers for CPU-bound simulations."""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List


def _spin(seconds: float) -> int:
    """Busy-loop for ~seconds and return worker pid."""
    end = time.perf_counter() + seconds
    x = 0.0
    while time.perf_counter() < end:
        x = (x + 1.0) * 1.0000001
    return os.getpid()


def verify_parallelism(workers: int, *, seconds: float = 1.0) -> Dict[str, object]:
    """Verify ProcessPool parallelism using CPU-bound tasks.

    Raises RuntimeError if the executor does not start enough workers or
    if wall time indicates no parallel speedup.
    """
    if workers < 2:
        raise RuntimeError("workers must be >= 2 for parallel verification")

    tasks = workers
    try:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            # warm up workers to avoid counting process start-up overhead
            warm_seconds = min(0.05, seconds / 10.0)
            warm = [ex.submit(_spin, warm_seconds) for _ in range(workers)]
            for f in warm:
                f.result()
            start = time.perf_counter()
            pids = [f.result() for f in (ex.submit(_spin, seconds) for _ in range(tasks))]
            elapsed = time.perf_counter() - start
    except PermissionError as exc:
        raise RuntimeError(
            "ProcessPool unavailable (failed to create SemLock). "
            "If running in a restricted sandbox, rerun with --allow-thread-fallback "
            "or run outside the sandbox to enable multiprocessing."
        ) from exc

    unique_pids = sorted(set(pids))
    if len(unique_pids) < min(workers, tasks):
        raise RuntimeError(f"Expected >= {min(workers, tasks)} worker pids, got {len(unique_pids)}: {unique_pids}")

    serial_time = seconds * tasks
    speedup_threshold = serial_time * 0.9
    if elapsed > speedup_threshold:
        raise RuntimeError(
            f"Parallel verification too slow: elapsed {elapsed:.3f}s "
            f"exceeds speedup threshold {speedup_threshold:.3f}s "
            f"(serial_time={serial_time:.3f}s)"
        )

    return {
        "mode": "processpool",
        "effective_workers": workers,
        "worker_pids": unique_pids,
        "elapsed_s": elapsed,
        "serial_time_s": serial_time,
        "speedup_threshold_s": speedup_threshold,
    }
