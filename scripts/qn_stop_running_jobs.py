"""Stop running QN simulation jobs by pattern."""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import time
from typing import List


DEFAULT_PATTERNS = [
    "qn_run_topology_policy_upgrade_curves",
    "qn_entanglement_service",
    "qn_.*robustness",
    "python .*scripts/qn_",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Stop running QN simulation jobs by pattern.")
    p.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Additional pattern(s) for pgrep -af (can be repeated).",
    )
    p.add_argument(
        "--no-defaults",
        action="store_true",
        help="Do not include default patterns; use only --pattern values.",
    )
    return p.parse_args()


def find_pids(patterns: List[str]) -> List[int]:
    pattern = "|".join(patterns)
    try:
        output = subprocess.check_output(["pgrep", "-af", pattern], text=True)
    except subprocess.CalledProcessError:
        return []
    pids = []
    for line in output.strip().splitlines():
        parts = line.strip().split(None, 1)
        if not parts:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        pids.append(pid)
    return sorted(set(pids))


def kill_pids(pids: List[int], sig: int) -> None:
    for pid in pids:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            continue


def main() -> None:
    args = parse_args()
    patterns = args.pattern if args.no_defaults else DEFAULT_PATTERNS + args.pattern
    pids = find_pids(patterns)
    if not pids:
        print("No matching processes found.")
        return
    print("Stopping processes:")
    for pid in pids:
        print(f"  PID {pid}")
    kill_pids(pids, signal.SIGINT)
    time.sleep(2)
    kill_pids(pids, signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline:
        remaining = [pid for pid in pids if os.path.exists(f"/proc/{pid}")]
        if not remaining:
            print("All processes terminated.")
            return
        time.sleep(0.5)
    print("Forcing remaining processes:")
    kill_pids(remaining, signal.SIGKILL)


if __name__ == "__main__":
    main()
