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
    nsfnet_topology,
    build_topology_from_dist_map,
    pick_upgrade_edges,
    edge_usage_counts_for_pairs,
    orig_edges_in_path,
)
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service


def parse_list(raw: str, cast=float):
    return [cast(x) for x in raw.split(",") if x]


def parse_args():
    p = argparse.ArgumentParser(description="Calibrate entanglement-service params on a fixed pair.")
    p.add_argument("--src", type=str, default="1")
    p.add_argument("--dst", type=str, default="14")
    p.add_argument("--strategy", type=str, default="EQT", choices=["BK", "EQT"])
    p.add_argument("--etas", type=str, default="0.9")
    p.add_argument("--upgrade-k-list", type=str, default="0")
    p.add_argument(
        "--upgrade-policy",
        choices=["global_rank", "pair_demand", "pair_path_only"],
        default="global_rank",
    )
    p.add_argument("--pairs-csv", type=Path, default=None, help="Pairs CSV for pair_demand policy.")
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
    p.add_argument("--network-scope", choices=["shortest_path", "full"], default="shortest_path")
    p.add_argument("--swap-schedule", choices=["sequential", "balanced"], default="sequential")
    p.add_argument("--debug-stats", action="store_true")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--topology-id", type=str, default="nsfnet")
    p.add_argument("--out-csv", type=Path, default=Path("out/qn_calibrate_pair.csv"))
    return p.parse_args()


def main():
    args = parse_args()
    if args.workers < 2 or args.workers > 10:
        raise SystemExit("workers must be between 2 and 10")
    etas = parse_list(args.etas, float)
    loads = parse_list(args.loads, float)
    seeds = parse_list(args.seeds, int)
    upgrade_ks = parse_list(args.upgrade_k_list, int)

    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
    expanded_edges, mapping, virtual_nodes = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
    if args.network_scope == "shortest_path":
        path_edges = shortest_path_edges(expanded_edges, args.src, args.dst)
        if not path_edges:
            raise SystemExit(f"No path between {args.src} and {args.dst}")
    else:
        path_edges = expanded_edges

    topo = nsfnet_topology()
    if args.edge_distance_csv:
        topo = build_topology_from_dist_map(dist_map)
    upgrade_edges_cache = {}
    if args.upgrade_policy == "global_rank":
        upgrade_edges_cache = {uk: set(pick_upgrade_edges(topo, "shortestpath_count", uk)) for uk in upgrade_ks}
    elif args.upgrade_policy == "pair_demand":
        pair_list = []
        if args.pairs_csv and args.pairs_csv.exists():
            with args.pairs_csv.open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pair_list.append((row["src"], row["dst"]))
        if not pair_list:
            pair_list = [(args.src, args.dst)]
        counts = edge_usage_counts_for_pairs(expanded_edges, pair_list)
        ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        for uk in upgrade_ks:
            upgrade_edges_cache[uk] = set([e for e, _ in ranked[:uk]])

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
                "topology_id",
                "upgrade_policy",
                "strategy",
                "upgrade_k",
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
                "eg_success_events",
                "swap_attempts",
                "swap_success",
                "swap_fail",
                "mem_expired_events",
                "swap_schedule",
            ]
        )
        for eta in etas:
            for load in loads:
                for uk in upgrade_ks:
                    if args.upgrade_policy == "pair_path_only":
                        path_orig_edges = orig_edges_in_path(path_edges)
                        upgraded_edges = set(path_orig_edges[:uk])
                    else:
                        upgraded_edges = upgrade_edges_cache.get(uk, set())
                    for seed in seeds:
                        edge_params: Dict[Tuple[str, str], EdgeParams] = {}
                        for a, b, dist_m, orig in path_edges:
                            dist_km = dist_m / 1000.0
                            if args.strategy == "BK":
                                use_strat = "BK"
                            else:
                                use_strat = "EQT" if orig in upgraded_edges else "BK"
                            p_eg, attempt_rate, coherence, p_bsm_edge, extra_lat = edge_params_for_strategy(
                                use_strat, dist_km, eta, knobs
                            )
                            edge_params[tuple(sorted((a, b)))] = EdgeParams(
                                attempt_rate_hz=attempt_rate,
                                p_eg=p_eg,
                                coherence_time_s=coherence,
                                extra_latency_s=extra_lat,
                            )
                        p_bsm, swap_lat = swap_params_for_strategy(args.strategy, knobs)
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
                            debug_stats=args.debug_stats,
                        )
                        stats = res.get("debug_stats") or {}
                        writer.writerow(
                            [
                                args.topology_id,
                                args.upgrade_policy,
                                args.strategy,
                                uk,
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
                                stats.get("eg_success_events", ""),
                                stats.get("swap_attempts", ""),
                                stats.get("swap_success", ""),
                                stats.get("swap_fail", ""),
                                stats.get("mem_expired_events", ""),
                                args.swap_schedule,
                            ]
                        )
    print(f"Wrote calibration grid to {args.out_csv}")


if __name__ == "__main__":
    main()
