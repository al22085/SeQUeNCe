"""Calibrate entanglement-service params on a fixed pair to exit zero-delivery regime."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    load_distance_dataset,
    load_edge_distances_csv,
    subdivide_edges,
    shortest_path_edges,
)
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service


def parse_list(raw: str, cast=float):
    return [cast(x) for x in raw.split(",") if x]


def parse_args():
    p = argparse.ArgumentParser(description="Calibrate entanglement-service params on a fixed pair.")
    p.add_argument("--src", type=str, default="1")
    p.add_argument("--dst", type=str, default="14")
    p.add_argument("--etas", type=str, default="0.9")
    p.add_argument("--loads", type=str, default="0.01,0.05,0.1,0.5,1.0")
    p.add_argument("--seeds", type=str, default="0,1")
    p.add_argument("--horizon-s", type=float, default=0.5)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=1e4)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=2e4)
    p.add_argument("--coherence-opt-s", type=float, default=0.05)
    p.add_argument("--coherence-sc-s", type=float, default=0.05)
    p.add_argument("--p-bsm-opt", type=float, default=0.9)
    p.add_argument("--p-bsm-sc", type=float, default=0.95)
    p.add_argument("--loss-db-per-km", type=float, default=0.2)
    p.add_argument("--transduction-latency-s", type=float, default=0.0)
    p.add_argument("--swap-latency-s", type=float, default=0.0)
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--edge-distance-csv", type=Path, default=None)
    p.add_argument(
        "--distance-dataset-id",
        type=str,
        default="topologybench_nsfnet13",
        help="Distance dataset id (sndlib_great_circle_heuristic | topologybench_nsfnet13)",
    )
    p.add_argument("--otp-data-rate-bps", type=float, default=1e3)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--key-bits-per-pair", type=float, default=1.0)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out-csv", type=Path, default=Path("out/qn_calibrate_pair.csv"))
    return p.parse_args()


def main():
    args = parse_args()
    etas = parse_list(args.etas, float)
    loads = parse_list(args.loads, float)
    seeds = parse_list(args.seeds, int)

    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
    expanded_edges, mapping, virtual_nodes = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
    path_edges = shortest_path_edges(expanded_edges, args.src, args.dst)
    if not path_edges:
        raise SystemExit(f"No path between {args.src} and {args.dst}")

    knobs = StrategyKnobs(
        attempt_rate_opt_hz=args.attempt_rate_opt_hz,
        attempt_rate_sc_hz=args.attempt_rate_sc_hz,
        p_bsm_opt=args.p_bsm_opt,
        p_bsm_sc=args.p_bsm_sc,
        coherence_opt_s=args.coherence_opt_s,
        coherence_sc_s=args.coherence_sc_s,
        loss_db_per_km=args.loss_db_per_km,
        transduction_latency_s=args.transduction_latency_s,
        swap_latency_s=args.swap_latency_s,
    )

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "src",
                "dst",
                "eta",
                "load",
                "seed",
                "availability",
                "served",
                "total",
                "bits_requested",
                "bits_delivered",
                "delivered_pairs",
            ]
        )
        for eta in etas:
            for load in loads:
                for seed in seeds:
                    edge_params: Dict[Tuple[str, str], EdgeParams] = {}
                    for a, b, dist_m, orig in path_edges:
                        dist_km = dist_m / 1000.0
                        p_eg, attempt_rate, coherence, p_bsm_edge, extra_lat = edge_params_for_strategy(
                            "EQT", dist_km, eta, knobs
                        )
                        edge_params[tuple(sorted((a, b)))] = EdgeParams(
                            attempt_rate_hz=attempt_rate,
                            p_eg=p_eg,
                            coherence_time_s=coherence,
                            extra_latency_s=extra_lat,
                        )
                    p_bsm, swap_lat = swap_params_for_strategy("EQT", knobs)
                    chain_path = []
                    for a, b, _, _ in path_edges:
                        if not chain_path:
                            chain_path.append(a)
                        chain_path.append(b)
                    res = simulate_entanglement_service(
                        path=chain_path,
                        edge_params=edge_params,
                        swap_params=SwapParams(p_bsm=p_bsm, latency_s=swap_lat),
                        seed=seed,
                        horizon_s=args.horizon_s,
                        tau_s=args.tau_s,
                        num_requests=0,
                        lambda_req=load,
                        otp_data_rate_bps=args.otp_data_rate_bps,
                        otp_session_duration_s=args.otp_session_duration_s,
                        otp_directions=args.otp_directions,
                        key_bits_per_pair=args.key_bits_per_pair,
                    )
                    writer.writerow(
                        [
                            args.src,
                            args.dst,
                            eta,
                            load,
                            seed,
                            res["availability"],
                            res["served"],
                            res["total"],
                            res["bits_requested"],
                            res["bits_delivered"],
                            res["ab_pairs"],
                        ]
                    )
    print(f"Wrote calibration grid to {args.out_csv}")


if __name__ == "__main__":
    main()
