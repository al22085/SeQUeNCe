"""Parallelism helpers for CPU-bound simulations."""

from __future__ import annotations

import os
import sys
import time
import math
import subprocess
import getpass
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


def _parse_cpu_max(path: Path) -> float | None:
    if not path.exists():
        return None
    raw = path.read_text().strip().split()
    if len(raw) != 2:
        return None
    quota, period = raw
    if quota == "max":
        return None
    try:
        quota_us = float(quota)
        period_us = float(period)
    except ValueError:
        return None
    if period_us <= 0:
        return None
    return quota_us / period_us


def _parse_cpuset_list(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    count = 0
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start_s, end_s = part.split("-", 1)
            try:
                start = int(start_s)
                end = int(end_s)
            except ValueError:
                return None
            count += max(0, end - start + 1)
        else:
            try:
                int(part)
            except ValueError:
                return None
            count += 1
    return count or None


def get_cpu_limit() -> tuple[float | None, str]:
    """Return (cpu_limit, reason). cpu_limit None means unlimited."""
    cpu_max = _parse_cpu_max(Path("/sys/fs/cgroup/cpu.max"))
    cpuset_path = Path("/sys/fs/cgroup/cpuset.cpus.effective")
    if not cpuset_path.exists():
        cpuset_path = Path("/sys/fs/cgroup/cpuset.cpus")
    cpuset_raw = cpuset_path.read_text().strip() if cpuset_path.exists() else ""
    cpuset_count = _parse_cpuset_list(cpuset_raw)
    limits = []
    reasons = []
    if cpu_max is not None:
        limits.append(cpu_max)
        reasons.append(f"cpu.max={cpu_max:.2f}")
    if cpuset_count is not None:
        limits.append(float(cpuset_count))
        reasons.append(f"cpuset={cpuset_count}")
    if not limits:
        return None, "unlimited"
    return min(limits), "+".join(reasons)


def normalize_workers(requested: int, *, min_workers: int = 2, max_workers: int = 20) -> tuple[int, float | None, str]:
    if requested < min_workers or requested > max_workers:
        raise RuntimeError(f"workers must be between {min_workers} and {max_workers}")
    limit, reason = get_cpu_limit()
    if limit is None:
        return requested, None, reason
    effective = int(max(1, math.floor(limit)))
    if effective < min_workers:
        raise RuntimeError(
            f"CPU limit too low for requested parallelism: limit={limit:.2f} ({reason}). "
            f"Require >= {min_workers} CPUs."
        )
    if effective < requested:
        return effective, limit, reason
    return requested, limit, reason


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
    task_seconds: float = 3.0,
    num_tasks: int | None = None,
    overhead_factor: float = 3.0,
    mp_context: mp.context.BaseContext | None = None,
) -> Dict[str, object]:
    """Verify ProcessPool parallelism using CPU-bound tasks.

    pid_only: require distinct worker PIDs, no speedup threshold.
    speedup: additionally enforce wall-time speedup vs serial baseline.
    pid_activity: require distinct PIDs and high CPU activity across workers.
    """
    if workers < 2:
        raise RuntimeError("workers must be >= 2 for parallel verification")
    if mode not in ("pid_only", "speedup", "pid_activity"):
        raise RuntimeError(f"Unknown verify mode: {mode}")

    if num_tasks is None:
        num_tasks = workers * 4 if mode in ("speedup", "pid_activity") else workers * 2

    ctx = mp_context or get_mp_context()
    start_method = ctx.get_start_method()
    shm_ok = _shm_ok()

    try:
        with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as ex:
            warm_seconds = min(0.05, task_seconds / 10.0)
            warm = [ex.submit(_spin, warm_seconds) for _ in range(workers)]
            warm_pids = [f.result() for f in warm]
            unique_pids = sorted(set(warm_pids))
            start = time.perf_counter()
            futures = [ex.submit(_spin, task_seconds) for _ in range(num_tasks)]
            ps_snapshot = ""
            worker_cpu = {}
            active_workers = 0
            aggregate_cpu = 0.0
            if mode == "pid_activity":
                time.sleep(min(0.5, task_seconds / 2.0))
                pid_list = ",".join(str(pid) for pid in unique_pids)
                ps_cmd = ["ps", "-p", pid_list, "-o", "pid,ppid,stat,%cpu,cmd"]
                try:
                    ps_snapshot = subprocess.check_output(ps_cmd, text=True)
                except subprocess.CalledProcessError:
                    ps_cmd = [
                        "ps",
                        "-u",
                        getpass.getuser(),
                        "-o",
                        "pid,ppid,stat,%cpu,cmd",
                        "--sort=-%cpu",
                    ]
                    ps_snapshot = subprocess.check_output(ps_cmd, text=True)
                for line in ps_snapshot.splitlines()[1:]:
                    parts = line.split(None, 4)
                    if len(parts) < 5:
                        continue
                    pid_s, _, stat, cpu_s, _ = parts
                    try:
                        pid = int(pid_s)
                        cpu = float(cpu_s)
                    except ValueError:
                        continue
                    if pid in unique_pids:
                        worker_cpu[pid] = (stat, cpu)
                        aggregate_cpu += cpu
                        if cpu >= 50.0:
                            active_workers += 1
            pids = [f.result() for f in futures]
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

    if mode != "pid_activity":
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
    if mode == "pid_activity":
        if active_workers < max(1, math.floor(0.8 * workers)):
            raise RuntimeError(
                f"Parallel verification: too few active workers ({active_workers}/{workers}). "
                "Likely idle workers or chunking too coarse. "
                f"worker_pids={unique_pids} aggregate_cpu={aggregate_cpu:.1f}%"
            )
        if aggregate_cpu < workers * 50.0:
            raise RuntimeError(
                f"Parallel verification: aggregate CPU {aggregate_cpu:.1f}% too low for {workers} workers. "
                "Check cgroup/cpuset limits or task granularity."
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
        "ps_snapshot": ps_snapshot,
        "worker_cpu": worker_cpu,
        "active_workers": active_workers,
        "aggregate_cpu": aggregate_cpu,
    }
