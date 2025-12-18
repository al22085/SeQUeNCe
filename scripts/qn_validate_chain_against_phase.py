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
    p.add_argument("--attempt-rate-hz", type=float, default=None, help="Override if not present in phase row.")
    p.add_argument("--p-eg", type=float, default=None)
    p.add_argument("--coherence-time-s", type=float, default=None)
    p.add_argument("--p-bsm", type=float, default=None)
    p.add_argument("--key-bits-per-pair", type=float, default=None)
    p.add_argument("--tolerance", type=float, default=0.05, help="Acceptable absolute difference.")
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
    attempt_rate = float(row.get("attempt_rate_hz") or args.attempt_rate_hz or 1e5)
    p_eg = float(row.get("p_eg") or args.p_eg or 0.2)
    coherence = float(row.get("coherence_time_s") or args.coherence_time_s or 0.02)
    p_bsm = float(row.get("p_bsm") or args.p_bsm or 0.9)
    kb = float(row.get("key_bits_per_pair") or args.key_bits_per_pair or 1.0)

    path = ["A", "R1", "R2", "B"]
    edges = [tuple(sorted((path[i], path[i + 1]))) for i in range(len(path) - 1)]
    edge_params = {e: EdgeParams(attempt_rate, p_eg, coherence) for e in edges}
    swap_params = SwapParams(p_bsm, 0.0)
    res = simulate_entanglement_service(
        path,
        edge_params,
        swap_params,
        seed=seed,
        horizon_s=deadline_s,
        tau_s=deadline_s,
        num_requests=num_trials,
        key_bits_per_pair=kb,
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
