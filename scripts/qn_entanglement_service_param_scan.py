"""Parameter scan to find non-zero deliveries on expanded NSFNET."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    nsfnet_topology,
    load_distance_dataset,
    load_edge_distances_csv,
    subdivide_edges,
    expanded_nodes,
    shortest_path_edges,
    pick_upgrade_edges,
)
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service


def parse_list(raw: str, cast=float):
    return [cast(x) for x in raw.split(",") if x]


def parse_args():
    p = argparse.ArgumentParser(description="Scan entanglement-service params to locate non-zero deliveries.")
    p.add_argument("--attempt-rate-opt-list", type=str, default="1e3,1e4")
    p.add_argument("--attempt-rate-sc-list", type=str, default="1e3,1e4")
    p.add_argument("--coherence-opt-list", type=str, default="0.02")
    p.add_argument("--coherence-sc-list", type=str, default="0.03")
    p.add_argument("--horizon-list", type=str, default="0.2")
    p.add_argument("--tau-list", type=str, default="0.05")
    p.add_argument("--eta", type=float, default=0.5)
    p.add_argument("--strategy", choices=["BK", "EQT"], default="BK")
    p.add_argument("--upgrade-k", type=int, default=0)
    p.add_argument("--upgrade-policy", choices=["shortestpath_count", "betweenness"], default="shortestpath_count")
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--edge-distance-csv", type=Path, default=None)
    p.add_argument(
        "--distance-dataset-id",
        type=str,
        default="topologybench_nsfnet13",
        help="Distance dataset id (sndlib_great_circle_heuristic | topologybench_nsfnet13)",
    )
    p.add_argument("--num-requests", type=int, default=20)
    p.add_argument("--lambda-req", type=float, default=0.5)
    p.add_argument("--otp-data-rate-bps", type=float, default=1e3)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--key-bits-per-pair", type=float, default=1.0)
    p.add_argument("--seeds", type=str, default="0,1")
    p.add_argument("--pair-mode", choices=["fixed", "random"], default="fixed")
    p.add_argument("--src-node", type=str, default="1")
    p.add_argument("--dst-node", type=str, default="14")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_ent_param_scan"))
    return p.parse_args()


def main():
    args = parse_args()
    seeds = parse_list(args.seeds, int)
    att_opt = parse_list(args.attempt_rate_opt_list, float)
    att_sc = parse_list(args.attempt_rate_sc_list, float)
    coh_opt = parse_list(args.coherence_opt_list, float)
    coh_sc = parse_list(args.coherence_sc_list, float)
    horizons = parse_list(args.horizon_list, float)
    taus = parse_list(args.tau_list, float)

    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
    expanded_edges, mapping, virtual_nodes = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
    nodes_list = expanded_nodes(expanded_edges)
    topo = nsfnet_topology()
    upgraded = set(pick_upgrade_edges(topo, args.upgrade_policy, args.upgrade_k))

    def choose_pair(seed: int):
        if args.pair_mode == "fixed":
            return args.src_node, args.dst_node
        rng = np.random.default_rng(seed)
        if len(nodes_list) < 2:
            return args.src_node, args.dst_node
        src_idx = rng.integers(0, len(nodes_list))
        dst_idx = rng.integers(0, len(nodes_list) - 1)
        if dst_idx >= src_idx:
            dst_idx += 1
        return nodes_list[src_idx], nodes_list[dst_idx]

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "param_scan.csv"
    headers = [
        "attempt_rate_opt_hz",
        "attempt_rate_sc_hz",
        "coherence_opt_s",
        "coherence_sc_s",
        "horizon_s",
        "tau_s",
        "seed",
        "src",
        "dst",
        "served",
        "total",
        "availability",
        "bits_requested",
        "bits_delivered",
    ]
    with raw_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for a_opt in att_opt:
            for a_sc in att_sc:
                for c_opt in coh_opt:
                    for c_sc in coh_sc:
                        knobs = StrategyKnobs(
                            attempt_rate_opt_hz=a_opt,
                            attempt_rate_sc_hz=a_sc,
                            coherence_opt_s=c_opt,
                            coherence_sc_s=c_sc,
                            p_bsm_opt=0.9,
                            p_bsm_sc=0.95,
                            loss_db_per_km=0.2,
                        )
                        p_bsm, swap_lat = swap_params_for_strategy(args.strategy, knobs)
                        for horizon in horizons:
                            for tau in taus:
                                for seed in seeds:
                                    src, dst = choose_pair(seed)
                                    path_edges = shortest_path_edges(expanded_edges, src, dst)
                                    edge_params = {}
                                    for a, b, dist_m, orig in path_edges:
                                        dist_km = dist_m / 1000.0
                                        use_strat = args.strategy if (args.strategy == "BK" or orig in upgraded) else "BK"
                                        p_eg, attempt_rate, coherence, p_bsm_edge, extra_lat = edge_params_for_strategy(
                                            use_strat, dist_km, args.eta, knobs
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
                                    res = simulate_entanglement_service(
                                        path=chain_path,
                                        edge_params=edge_params,
                                        swap_params=SwapParams(p_bsm=p_bsm, latency_s=swap_lat),
                                        seed=seed,
                                        horizon_s=horizon,
                                        tau_s=tau,
                                        num_requests=args.num_requests,
                                        lambda_req=args.lambda_req,
                                        otp_data_rate_bps=args.otp_data_rate_bps,
                                        otp_session_duration_s=args.otp_session_duration_s,
                                        otp_directions=args.otp_directions,
                                        key_bits_per_pair=args.key_bits_per_pair,
                                    )
                                    writer.writerow(
                                        [
                                            a_opt,
                                            a_sc,
                                            c_opt,
                                            c_sc,
                                            horizon,
                                            tau,
                                            seed,
                                            src,
                                            dst,
                                            res["served"],
                                            res["total"],
                                            res["availability"],
                                            res["bits_requested"],
                                            res["bits_delivered"],
                                        ]
                                    )
    print(f"Wrote scan results to {raw_path}")


if __name__ == "__main__":
    main()
