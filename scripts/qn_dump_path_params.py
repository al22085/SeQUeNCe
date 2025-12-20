"""Dump per-segment parameters along shortest path for given src/dst."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import load_distance_dataset, load_edge_distances_csv, subdivide_edges, shortest_path_edges
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy


def parse_args():
    p = argparse.ArgumentParser(description="Dump per-segment params for shortest path.")
    p.add_argument("--src-node", type=str, required=True)
    p.add_argument("--dst-node", type=str, required=True)
    p.add_argument("--edge-distance-csv", type=Path, default=None)
    p.add_argument("--distance-dataset-id", type=str, default="topologybench_nsfnet13")
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--eta", type=float, default=0.9)
    p.add_argument("--loss-db-per-km", type=float, default=0.2)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=1e4)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=2e4)
    p.add_argument("--coherence-opt-s", type=float, default=0.05)
    p.add_argument("--coherence-sc-s", type=float, default=0.1)
    p.add_argument("--p-bsm-opt", type=float, default=0.9)
    p.add_argument("--p-bsm-sc", type=float, default=0.95)
    p.add_argument("--strategy", choices=["BK", "EQT", "DQT"], default="BK")
    p.add_argument("--upgrade-k", type=int, default=0)
    p.add_argument("--horizon-s", type=float, default=0.5)
    return p.parse_args()


def main():
    args = parse_args()
    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
    expanded_edges, mapping, virtual_nodes = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
    path = shortest_path_edges(expanded_edges, args.src_node, args.dst_node)
    if not path:
        raise SystemExit(f"No path {args.src_node}->{args.dst_node}")

    knobs = StrategyKnobs(
        attempt_rate_opt_hz=args.attempt_rate_opt_hz,
        attempt_rate_sc_hz=args.attempt_rate_sc_hz,
        p_bsm_opt=args.p_bsm_opt,
        p_bsm_sc=args.p_bsm_sc,
        coherence_opt_s=args.coherence_opt_s,
        coherence_sc_s=args.coherence_sc_s,
        loss_db_per_km=args.loss_db_per_km,
    )
    p_bsm, _ = swap_params_for_strategy(args.strategy, knobs)

    print(f"Path {args.src_node}->{args.dst_node} segments={len(path)} strategy={args.strategy} upgrade_k={args.upgrade_k} horizon_s={args.horizon_s}")
    print("segment_idx,orig_edge,segment_km,p_eg,attempt_rate_hz,success_rate_hz,coherence_s,p_bsm")
    for idx, (a, b, dist_m, orig) in enumerate(path):
        dist_km = dist_m / 1000.0
        use_strategy = args.strategy  # upgrade handling is external; treat EQT if strategy=EQT
        p_eg, attempt_rate, coherence, p_bsm_edge, extra_lat = edge_params_for_strategy(use_strategy, dist_km, args.eta, knobs)
        success_rate = attempt_rate * p_eg
        print(
            f"{idx},{orig[0]}-{orig[1]},{dist_km:.3f},{p_eg:.3e},{attempt_rate:.3e},{success_rate:.3e},{coherence:.3e},{p_bsm_edge:.3f}"
        )
        expected = success_rate * args.horizon_s
    total_km = sum(seg[2] for seg in path) / 1000.0
    print(f"Total path km (segments sum): {total_km:.3f}")


if __name__ == "__main__":
    main()
