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
from typing import Dict, Tuple


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


def _read_proc_self_cgroup() -> Tuple[str | None, Dict[str, str]]:
    v2_path = None
    v1_paths: Dict[str, str] = {}
    try:
        raw = Path("/proc/self/cgroup").read_text().splitlines()
    except OSError:
        return None, {}
    for line in raw:
        parts = line.strip().split(":", 2)
        if len(parts) != 3:
            continue
        subsystems = parts[1]
        path = parts[2]
        if subsystems == "":
            v2_path = path
        else:
            for sub in subsystems.split(","):
                v1_paths[sub] = path
    return v2_path, v1_paths


def _parse_mountinfo() -> Tuple[str | None, Dict[str, str]]:
    cgroup2_mount = None
    cgroup_mounts: Dict[str, str] = {}
    try:
        raw = Path("/proc/self/mountinfo").read_text().splitlines()
    except OSError:
        return None, {}
    for line in raw:
        if " - " not in line:
            continue
        pre, post = line.split(" - ", 1)
        pre_fields = pre.split()
        post_fields = post.split()
        if len(pre_fields) < 5 or len(post_fields) < 3:
            continue
        mountpoint = pre_fields[4]
        fstype = post_fields[0]
        superopts = post_fields[2]
        if fstype == "cgroup2":
            cgroup2_mount = mountpoint
        elif fstype == "cgroup":
            subs = superopts.split(",")
            for sub in subs:
                if sub in ("cpu", "cpuset"):
                    cgroup_mounts[sub] = mountpoint
    return cgroup2_mount, cgroup_mounts


def _read_cpu_stat(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {}
    out: Dict[str, int] = {}
    for line in path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) != 2:
            continue
        key, val = parts
        try:
            out[key] = int(val)
        except ValueError:
            continue
    return out


def detect_cpu_limit() -> Dict[str, object]:
    affinity_cpus = None
    try:
        affinity_cpus = len(os.sched_getaffinity(0))
    except (AttributeError, OSError):
        affinity_cpus = os.cpu_count()

    v2_path, v1_paths = _read_proc_self_cgroup()
    cgroup2_mount, cgroup_mounts = _parse_mountinfo()

    cg_version = None
    cpu_max = None
    cpuset_cores = None
    quota_cores = None
    cpu_stat_path = None
    cg_path = None

    if cgroup2_mount and v2_path is not None:
        cg_version = "v2"
        cg_path = str(Path(cgroup2_mount) / v2_path.lstrip("/"))
        cg_dir = Path(cg_path)
        cpu_max = _parse_cpu_max(cg_dir / "cpu.max")
        quota_cores = cpu_max
        cpuset_path = cg_dir / "cpuset.cpus.effective"
        if not cpuset_path.exists():
            cpuset_path = Path(cgroup2_mount) / "cpuset.cpus.effective"
        if cpuset_path.exists():
            cpuset_cores = _parse_cpuset_list(cpuset_path.read_text())
        cpu_stat_path = cg_dir / "cpu.stat"
    else:
        cg_version = "v1"
        cpu_path = v1_paths.get("cpu") or v1_paths.get("cpuacct")
        if cpu_path and "cpu" in cgroup_mounts:
            cpu_dir = Path(cgroup_mounts["cpu"]) / cpu_path.lstrip("/")
            quota_path = cpu_dir / "cpu.cfs_quota_us"
            period_path = cpu_dir / "cpu.cfs_period_us"
            try:
                quota = int(quota_path.read_text().strip())
                period = int(period_path.read_text().strip())
                if quota > 0 and period > 0:
                    quota_cores = quota / period
            except OSError:
                pass
            cpu_stat_path = cpu_dir / "cpu.stat"
        cpuset_path = None
        cpuset_cg = v1_paths.get("cpuset")
        if cpuset_cg and "cpuset" in cgroup_mounts:
            cpuset_path = Path(cgroup_mounts["cpuset"]) / cpuset_cg.lstrip("/") / "cpuset.cpus"
            if cpuset_path.exists():
                cpuset_cores = _parse_cpuset_list(cpuset_path.read_text())

    limits = []
    reasons = []
    if affinity_cpus:
        limits.append(float(affinity_cpus))
        reasons.append(f"affinity={affinity_cpus}")
    if cpuset_cores:
        limits.append(float(cpuset_cores))
        reasons.append(f"cpuset={cpuset_cores}")
    if quota_cores:
        limits.append(float(quota_cores))
        reasons.append(f"quota={quota_cores:.2f}")

    effective_cpu_limit = min(limits) if limits else None
    return {
        "affinity_cpus": affinity_cpus,
        "cpuset_cores": cpuset_cores,
        "quota_cores": quota_cores,
        "effective_cpu_limit": effective_cpu_limit,
        "limit_reason": "+".join(reasons) if reasons else "unlimited",
        "cgroup_version": cg_version,
        "cgroup_path": cg_path,
        "cpu_stat_path": str(cpu_stat_path) if cpu_stat_path else "",
    }


def normalize_workers(requested: int, *, min_workers: int = 2, max_workers: int = 20) -> tuple[int, float | None, str]:
    if requested < min_workers or requested > max_workers:
        raise RuntimeError(f"workers must be between {min_workers} and {max_workers}")
    limit_info = detect_cpu_limit()
    limit = limit_info["effective_cpu_limit"]
    reason = limit_info["limit_reason"]
    if not limit:
        return requested, None, reason
    effective = int(max(1, math.floor(float(limit))))
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
    limit_info = detect_cpu_limit()
    cpu_stat_path = Path(limit_info["cpu_stat_path"]) if limit_info["cpu_stat_path"] else None
    cpu_stat_before = _read_cpu_stat(cpu_stat_path) if cpu_stat_path else {}

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
                pid_list = ",".join(str(pid) for pid in unique_pids)
                best_snapshot = ""
                best_active = 0
                best_agg = 0.0
                for _ in range(3):
                    time.sleep(max(0.5, task_seconds / 4.0))
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
                    worker_cpu = {}
                    active_workers = 0
                    aggregate_cpu = 0.0
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
                            if cpu >= 50.0 and "R" in stat:
                                active_workers += 1
                    if active_workers > best_active or aggregate_cpu > best_agg:
                        best_active = active_workers
                        best_agg = aggregate_cpu
                        best_snapshot = ps_snapshot
                    if active_workers >= max(1, math.floor(0.8 * workers)):
                        break
                active_workers = best_active
                aggregate_cpu = best_agg
                ps_snapshot = best_snapshot
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

    cpu_stat_after = _read_cpu_stat(cpu_stat_path) if cpu_stat_path else {}
    throttled_usec = cpu_stat_after.get("throttled_usec", 0) - cpu_stat_before.get("throttled_usec", 0)
    nr_throttled = cpu_stat_after.get("nr_throttled", 0) - cpu_stat_before.get("nr_throttled", 0)
    throttled_detected = throttled_usec > 0 or nr_throttled > 0

    serial_time = task_seconds * num_tasks
    expected_parallel = (serial_time / workers) * overhead_factor
    if mode == "speedup" and elapsed > expected_parallel:
        raise RuntimeError(
            f"Parallel verification too slow: elapsed {elapsed:.3f}s exceeds "
            f"expected_parallel {expected_parallel:.3f}s (serial_time={serial_time:.3f}s, "
            f"overhead_factor={overhead_factor:.2f})"
        )
    expected_cpu = 100.0 * min(
        workers,
        limit_info["effective_cpu_limit"] if limit_info["effective_cpu_limit"] else workers,
    )
    observed_cpu_limit = aggregate_cpu / 100.0 if aggregate_cpu else None
    if mode == "pid_activity":
        if active_workers < max(1, math.floor(0.8 * workers)):
            raise RuntimeError(
                f"Parallel verification: too few active workers ({active_workers}/{workers}). "
                "Likely idle workers or chunking too coarse. "
                f"worker_pids={unique_pids} aggregate_cpu={aggregate_cpu:.1f}%\n"
                f"ps_snapshot:\n{ps_snapshot}"
            )
        if aggregate_cpu < expected_cpu * 0.8 and not throttled_detected:
            raise RuntimeError(
                f"Parallel verification: aggregate CPU {aggregate_cpu:.1f}% below expected {expected_cpu:.1f}% "
                "without throttling; check chunking or scheduler."
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
        "expected_cpu": expected_cpu,
        "observed_cpu_limit": observed_cpu_limit,
        "throttled_detected": throttled_detected,
        "throttled_usec_delta": throttled_usec,
        "nr_throttled_delta": nr_throttled,
        "cpu_limit_info": limit_info,
    }
