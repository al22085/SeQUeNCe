"""Collect long-pair debug counters vs upgrade-k for BK and EQT."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    load_distance_dataset,
    load_edge_distances_csv,
    subdivide_edges,
    shortest_path_edges,
    nsfnet_topology,
    pick_upgrade_edges,
)
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service


def parse_args():
    p = argparse.ArgumentParser(description="Collect long-pair debug counters vs upgrade-k.")
    p.add_argument("--src", type=str, default="4")
    p.add_argument("--dst", type=str, default="6")
    p.add_argument("--etas", type=str, default="0.9")
    p.add_argument("--upgrade-k-list", type=str, default="0,3,7,21")
    p.add_argument("--strategies", type=str, default="BK,EQT")
    p.add_argument("--seeds", type=str, default="0,1,2,3")
    p.add_argument("--loads", type=str, default="0.01")
    p.add_argument("--horizon-s", type=float, default=0.3)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=5000)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=10000)
    p.add_argument("--coherence-opt-s", type=float, default=0.05)
    p.add_argument("--coherence-sc-s", type=float, default=0.1)
    p.add_argument("--p-bsm-opt", type=float, default=0.9)
    p.add_argument("--p-bsm-sc", type=float, default=0.95)
    p.add_argument("--loss-db-per-km", type=float, default=0.2)
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--edge-distance-csv", type=Path, default=None)
    p.add_argument("--distance-dataset-id", type=str, default="topologybench_nsfnet13")
    p.add_argument("--otp-data-rate-bps", type=float, default=1.0)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=1)
    p.add_argument("--key-bits-per-pair", type=float, default=1.0)
    p.add_argument("--swap-schedule", choices=["sequential", "balanced"], default="balanced")
    p.add_argument("--upgrade-policy", type=str, default="shortestpath_count")
    p.add_argument("--out-dir", type=Path, default=Path("out/upgrade_threshold_analysis"))
    p.add_argument("--workers", type=int, default=4)
    return p.parse_args()


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    etas = parse_list(args.etas, float)
    upgrade_ks = parse_list(args.upgrade_k_list, int)
    strategies = [s for s in args.strategies.split(",") if s]
    seeds = parse_list(args.seeds, int)
    loads = parse_list(args.loads, float)

    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
    expanded_edges, _, _ = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
    path_edges = shortest_path_edges(expanded_edges, args.src, args.dst)
    if not path_edges:
        raise SystemExit(f"No path between {args.src} and {args.dst}")

    topo = nsfnet_topology()
    upgrade_edges_cache = {k: set(pick_upgrade_edges(topo, args.upgrade_policy, k)) for k in upgrade_ks}

    knobs = StrategyKnobs(
        attempt_rate_opt_hz=args.attempt_rate_opt_hz,
        attempt_rate_sc_hz=args.attempt_rate_sc_hz,
        p_bsm_opt=args.p_bsm_opt,
        p_bsm_sc=args.p_bsm_sc,
        coherence_opt_s=args.coherence_opt_s,
        coherence_sc_s=args.coherence_sc_s,
        loss_db_per_km=args.loss_db_per_km,
    )

    raw_rows = []
    for eta_val in etas:
        for load in loads:
            for strat in strategies:
                ks = [0] if strat == "BK" else upgrade_ks
                for k in ks:
                    upgraded_edges = upgrade_edges_cache[k]
                    p_bsm, swap_lat = swap_params_for_strategy(strat, knobs)
                    for seed in seeds:
                        edge_params: Dict[Tuple[str, str], EdgeParams] = {}
                        for a, b, dist_m, orig in path_edges:
                            dist_km = dist_m / 1000.0
                            use_strat = strat if (strat == "BK" or orig in upgraded_edges) else "BK"
                            p_eg, attempt_rate, coherence, p_bsm_edge, extra_lat = edge_params_for_strategy(
                                use_strat, dist_km, eta_val, knobs
                            )
                            edge_params[tuple(sorted((a, b)))] = EdgeParams(
                                attempt_rate_hz=attempt_rate,
                                p_eg=p_eg,
                                coherence_time_s=coherence,
                                extra_latency_s=extra_lat,
                            )
                        chain_path = []
                        for a, b, _, _ in path_edges:
                            if not chain_path:
                                chain_path.append(a)
                            chain_path.append(b)
                        num_requests = max(1, int(round(load * 10)))
                        res = simulate_entanglement_service(
                            path=chain_path,
                            edge_params=edge_params,
                            swap_params=SwapParams(p_bsm=p_bsm, latency_s=swap_lat),
                            seed=seed,
                            horizon_s=args.horizon_s,
                            tau_s=args.tau_s,
                            num_requests=num_requests,
                            lambda_req=None,
                            otp_data_rate_bps=args.otp_data_rate_bps,
                            otp_session_duration_s=args.otp_session_duration_s,
                            otp_directions=args.otp_directions,
                            key_bits_per_pair=args.key_bits_per_pair,
                            swap_schedule=args.swap_schedule,
                            debug_stats=True,
                        )
                        stats = res["debug_stats"] or {}
                        raw_rows.append(
                            {
                                "src": args.src,
                                "dst": args.dst,
                                "eta": eta_val,
                                "strategy": strat,
                                "upgrade_k": k,
                                "load": load,
                                "seed": seed,
                                "delivered_pairs": res["ab_pairs"],
                                "bits_delivered": res["bits_delivered"],
                                "eg_success_events": stats.get("eg_success_events", 0),
                                "swap_attempts": stats.get("swap_attempts", 0),
                                "swap_success": stats.get("swap_success", 0),
                                "swap_fail": stats.get("swap_fail", 0),
                                "mem_expired_events": stats.get("mem_expired_events", 0),
                            }
                        )

    raw_path = args.out_dir / "longpair_counters_vs_k.csv"
    with raw_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "src",
                "dst",
                "eta",
                "strategy",
                "upgrade_k",
                "load",
                "seed",
                "delivered_pairs",
                "bits_delivered",
                "eg_success_events",
                "swap_attempts",
                "swap_success",
                "swap_fail",
                "mem_expired_events",
            ],
        )
        writer.writeheader()
        writer.writerows(raw_rows)

    # summary
    summary_rows = []
    for eta_val in etas:
        for load in loads:
            for strat in strategies:
                ks = [0] if strat == "BK" else upgrade_ks
                for k in ks:
                    rows = [
                        r for r in raw_rows
                        if r["eta"] == eta_val and r["load"] == load and r["strategy"] == strat and r["upgrade_k"] == k
                    ]
                    if not rows:
                        continue
                    swap_attempts = np.mean([r["swap_attempts"] for r in rows])
                    swap_fail = np.mean([r["swap_fail"] for r in rows])
                    swap_fail_rate = swap_fail / swap_attempts if swap_attempts > 0 else 0.0
                    summary_rows.append(
                        {
                            "eta": eta_val,
                            "strategy": strat,
                            "upgrade_k": k,
                            "load": load,
                            "delivered_pairs_mean": float(np.mean([r["delivered_pairs"] for r in rows])),
                            "bits_delivered_mean": float(np.mean([r["bits_delivered"] for r in rows])),
                            "eg_success_mean": float(np.mean([r["eg_success_events"] for r in rows])),
                            "swap_attempts_mean": float(swap_attempts),
                            "swap_success_mean": float(np.mean([r["swap_success"] for r in rows])),
                            "swap_fail_mean": float(swap_fail),
                            "swap_fail_rate_mean": float(swap_fail_rate),
                            "mem_expired_mean": float(np.mean([r["mem_expired_events"] for r in rows])),
                        }
                    )

    summary_path = args.out_dir / "longpair_counters_vs_k_summary.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(summary_rows[0].keys()) if summary_rows else [],
        )
        if summary_rows:
            writer.writeheader()
            writer.writerows(summary_rows)

    print(f"Wrote {raw_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
