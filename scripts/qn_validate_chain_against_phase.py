"""Validate chain entanglement service against a phase_raw row."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service


def parse_args():
    p = argparse.ArgumentParser(description="Compare entanglement_service availability to a phase_raw.csv row.")
    p.add_argument("--phase-raw", type=Path, required=True)
    p.add_argument("--row-index", type=int, default=0, help="Zero-based row index to validate.")
    p.add_argument("--attempt-rate-hz", type=float, default=1e5)
    p.add_argument("--p-eg", type=float, default=0.2)
    p.add_argument("--coherence-time-s", type=float, default=0.02)
    p.add_argument("--p-bsm", type=float, default=0.9)
    p.add_argument("--key-bits-per-pair", type=float, default=1.0)
    p.add_argument("--tolerance", type=float, default=0.2, help="Acceptable absolute difference.")
    return p.parse_args()


def main():
    args = parse_args()
    with args.phase_raw.open() as f:
        rows = list(csv.DictReader(f))
    if args.row_index >= len(rows):
        raise IndexError("row_index out of bounds")
    row = rows[args.row_index]
    num_trials = int(row["num_trials"])
    deadline_s = float(row["deadline_s"])
    availability_ref = float(row["availability_req"])
    seed = int(row["seed"])

    path = ["A", "R1", "R2", "B"]
    edges = [tuple(sorted((path[i], path[i + 1]))) for i in range(len(path) - 1)]
    edge_params = {e: EdgeParams(args.attempt_rate_hz, args.p_eg, args.coherence_time_s) for e in edges}
    swap_params = SwapParams(args.p_bsm, 0.0)
    res = simulate_entanglement_service(
        path,
        edge_params,
        swap_params,
        seed=seed,
        horizon_s=deadline_s,
        tau_s=deadline_s,
        num_requests=num_trials,
        key_bits_per_pair=args.key_bits_per_pair,
    )
    diff = abs(res["availability"] - availability_ref)
    ok = diff <= args.tolerance
    summary = {
        "availability_ref": availability_ref,
        "availability_sim": res["availability"],
        "diff": diff,
        "within_tolerance": ok,
    }
    print(json.dumps(summary, indent=2))
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
