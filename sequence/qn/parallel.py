"""Parallelism helpers for CPU-bound simulations."""

from __future__ import annotations

import os
import sys
import time
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict


def _spin(seconds: float) -> int:
    """Busy-loop for ~seconds and return worker pid."""
    end = time.perf_counter() + seconds
    x = 0.0
    while time.perf_counter() < end:
        x = (x + 1.0) * 1.0000001
    return os.getpid()


def _shm_ok() -> bool:
    shm = Path("/dev/shm")
    return shm.exists() and os.access(shm, os.W_OK)


def get_mp_context(start_method: str | None = None) -> mp.context.BaseContext:
    if start_method:
        return mp.get_context(start_method)
    if sys.platform.startswith("linux"):
        try:
            return mp.get_context("fork")
        except ValueError:
            return mp.get_context()
    return mp.get_context()


def verify_parallelism(
    workers: int,
    *,
    mode: str = "pid_only",
    task_seconds: float = 1.0,
    num_tasks: int | None = None,
    overhead_factor: float = 3.0,
    mp_context: mp.context.BaseContext | None = None,
) -> Dict[str, object]:
    """Verify ProcessPool parallelism using CPU-bound tasks.

    pid_only: require distinct worker PIDs, no speedup threshold.
    speedup: additionally enforce wall-time speedup vs serial baseline.
    """
    if workers < 2:
        raise RuntimeError("workers must be >= 2 for parallel verification")
    if mode not in ("pid_only", "speedup"):
        raise RuntimeError(f"Unknown verify mode: {mode}")

    if num_tasks is None:
        num_tasks = workers if mode == "pid_only" else workers * 4

    ctx = mp_context or get_mp_context()
    start_method = ctx.get_start_method()
    shm_ok = _shm_ok()

    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
            warm_seconds = min(0.05, task_seconds / 10.0)
            warm = [ex.submit(_spin, warm_seconds) for _ in range(workers)]
            for f in warm:
                f.result()
            start = time.perf_counter()
            pids = [f.result() for f in (ex.submit(_spin, task_seconds) for _ in range(num_tasks))]
            elapsed = time.perf_counter() - start
    except PermissionError as exc:
        hint = ""
        if sys.platform.startswith("linux") and start_method != "fork":
            hint = " Consider --mp-start-method fork on Linux."
        raise RuntimeError(
            "ProcessPool unavailable (failed to create SemLock). "
            f"start_method={start_method} shm_ok={shm_ok}.{hint} "
            "If running in a restricted sandbox, rerun with --allow-thread-fallback "
            "or run outside the sandbox to enable multiprocessing."
        ) from exc

    unique_pids = sorted(set(pids))
    if len(unique_pids) < min(workers, num_tasks):
        raise RuntimeError(
            f"Expected >= {min(workers, num_tasks)} worker pids, got {len(unique_pids)}: {unique_pids}"
        )

    serial_time = task_seconds * num_tasks
    expected_parallel = (serial_time / workers) * overhead_factor
    if mode == "speedup" and elapsed > expected_parallel:
        raise RuntimeError(
            f"Parallel verification too slow: elapsed {elapsed:.3f}s exceeds "
            f"expected_parallel {expected_parallel:.3f}s (serial_time={serial_time:.3f}s, "
            f"overhead_factor={overhead_factor:.2f})"
        )

    return {
        "mode": "processpool",
        "verify_mode": mode,
        "effective_workers": workers,
        "worker_pids": unique_pids,
        "elapsed_s": elapsed,
        "task_seconds": task_seconds,
        "num_tasks": num_tasks,
        "serial_time_s": serial_time,
        "expected_parallel_s": expected_parallel,
        "overhead_factor": overhead_factor,
        "start_method": start_method,
        "shm_ok": shm_ok,
    }
