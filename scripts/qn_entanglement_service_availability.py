"""CLI for entanglement service availability (EG+memory+swapping with retries)."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_experiment_presets import apply_preset
from scripts.qn_topologies import (
    nsfnet_topology,
    nsfnet_edges,
    load_edge_distances_csv,
    load_distance_dataset,
    build_topology_from_dist_map,
    subdivide_edges,
    expanded_nodes,
    shortest_path_edges,
    pick_upgrade_edges,
)
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service
from sequence.qn.parallel import normalize_workers
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Entanglement service availability with discrete-event EG + swapping retries.")
    p.add_argument("--topology", choices=["chain", "nsfnet"], default="chain")
    p.add_argument("--strategy", choices=["BK", "DQT", "EQT"], default="BK")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--seeds", type=str, default="")
    p.add_argument("--num-requests", type=int, default=20)
    p.add_argument("--lambda-req", type=float, default=None, help="If set, use Poisson arrivals; otherwise spread num-requests across horizon.")
    p.add_argument("--horizon-s", type=float, default=0.1)
    p.add_argument("--tau-s", type=float, default=0.05)
    p.add_argument("--eta", type=float, default=0.8)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=1e3)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=1e3)
    p.add_argument("--p-bsm-opt", type=float, default=0.9)
    p.add_argument("--p-bsm-sc", type=float, default=0.95)
    p.add_argument("--coherence-opt-s", type=float, default=0.02)
    p.add_argument("--coherence-sc-s", type=float, default=0.03)
    p.add_argument("--swap-latency-s", type=float, default=0.0)
    p.add_argument("--transduction-latency-s", type=float, default=0.0)
    p.add_argument("--key-bits-per-pair", type=float, default=1.0)
    p.add_argument("--key-bits-per-pair-list", type=str, default="", help="Optional list; if set, run all values.")
    p.add_argument("--otp-data-rate-bps", type=float, default=1e3)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--edge-params-csv", type=Path, default=None, help="CSV with u,v,attempt_rate_hz,p_eg,coherence_time_s")
    p.add_argument("--edge-distance-csv", type=Path, default=None, help="CSV with u,v,distance_m for NSFNET")
    p.add_argument(
        "--distance-dataset-id",
        type=str,
        default="sndlib_great_circle_heuristic",
        help="Distance dataset id (sndlib_great_circle_heuristic | topologybench_nsfnet13)",
    )
    p.add_argument("--p-eg-per-km", type=float, default=None, help="If set with distance map, compute p_eg=exp(-loss_db_per_km*dist_km) using loss_db_per_km= -10*log10(p_eg_per_km)")
    p.add_argument("--loss-db-per-km", type=float, default=0.2, help="Loss in dB/km for distance->p_eg mapping")
    p.add_argument("--upgrade-k", type=int, default=0, help="Top-k edges to upgrade to QT params (nsfnet only).")
    p.add_argument("--upgrade-policy", choices=["shortestpath_count", "betweenness"], default="shortestpath_count")
    p.add_argument("--upgrade-mode", choices=["edges", "repeaters"], default="edges")
    p.add_argument("--pair-mode", choices=["fixed", "random"], default="fixed")
    p.add_argument("--src-node", type=str, default="1")
    p.add_argument("--dst-node", type=str, default="14")
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--preset", type=str, default="")
    p.add_argument("--workers", type=int, default=2, help="Parallel workers (2..20).")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_entanglement_service"))
    p.add_argument("--resume", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    try:
        effective_workers, cpu_limit, cpu_reason = normalize_workers(args.workers, min_workers=2, max_workers=20)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if cpu_limit is not None and effective_workers < args.workers:
        print(f"WARNING: cpu_limit={cpu_limit:.2f} ({cpu_reason}); effective_workers={effective_workers}")
    args.workers = effective_workers
    args = apply_preset(args, args.preset)
    seeds = parse_list(args.seeds, int) if args.seeds else [args.seed]
    dist_map = {}
    if args.topology == "nsfnet":
        dist_map = load_distance_dataset(args.distance_dataset_id)
        if args.edge_distance_csv:
            dist_map = load_edge_distances_csv(args.edge_distance_csv)
        expanded_edges, mapping, virtual_nodes = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
        nodes_expanded = expanded_nodes(expanded_edges)
        topo = nsfnet_topology()
        if args.edge_distance_csv:
            topo = build_topology_from_dist_map(dist_map)
        upgrade_edges = set(pick_upgrade_edges(topo, args.upgrade_policy, args.upgrade_k))
    else:
        base_edges = [
            ("A", "R1", 1000.0, ("A", "R1")),
            ("R1", "R2", 1000.0, ("R1", "R2")),
            ("R2", "B", 1000.0, ("R2", "B")),
        ]
        expanded_edges, mapping, virtual_nodes = base_edges, {}, set()
        nodes_expanded = expanded_nodes(expanded_edges)
        upgrade_edges = set()

    knobs = StrategyKnobs(
        attempt_rate_opt_hz=args.attempt_rate_opt_hz,
        attempt_rate_sc_hz=args.attempt_rate_sc_hz,
        p_bsm_opt=args.p_bsm_opt,
        p_bsm_sc=args.p_bsm_sc,
        coherence_opt_s=args.coherence_opt_s,
        coherence_sc_s=args.coherence_sc_s,
        loss_db_per_km=args.loss_db_per_km,
        p_eg_per_km=args.p_eg_per_km,
        transduction_latency_s=args.transduction_latency_s,
        swap_latency_s=args.swap_latency_s,
    )

    if args.upgrade_mode != "edges":
        raise SystemExit("upgrade-mode repeaters not implemented; use edges")

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    kbits_list = parse_list(args.key_bits_per_pair_list, float) if args.key_bits_per_pair_list else [args.key_bits_per_pair]

    # fallbacks for fixed endpoints when user-specified nodes do not exist in graph
    default_src = args.src_node
    default_dst = args.dst_node
    if args.pair_mode == "fixed":
        if default_src not in nodes_expanded or default_dst not in nodes_expanded:
            if expanded_edges:
                default_src = expanded_edges[0][0]
                default_dst = expanded_edges[-1][1]

    def pick_pair(seed: int):
        if args.pair_mode == "fixed":
            return default_src, default_dst
        rng = np.random.default_rng(seed)
        candidates = sorted(nodes_expanded)
        if len(candidates) < 2:
            return args.src_node, args.dst_node
        src_idx = rng.integers(0, len(candidates))
        dst_idx = rng.integers(0, len(candidates) - 1)
        if dst_idx >= src_idx:
            dst_idx += 1
        return candidates[src_idx], candidates[dst_idx]

    for kb in kbits_list:
        subdir = out_dir / f"kbits_{kb}"
        subdir.mkdir(parents=True, exist_ok=True)
        raw_path = subdir / "entanglement_service_raw.csv"
        summary_path = subdir / "summary.json"
        raw_headers = [
            "seed",
            "src",
            "dst",
            "request_idx",
            "arrival_s",
            "deadline_s",
            "served",
            "t_done_s",
            "bits_needed",
            "bits_delivered",
        ]
        mode = "a" if (args.resume and raw_path.exists()) else "w"
        with raw_path.open(mode, newline="") as f_raw:
            writer = csv.writer(f_raw)
            if mode == "w":
                writer.writerow(raw_headers)

            availabilities = []
            for s in seeds:
                src, dst = pick_pair(s)
                path_edges = shortest_path_edges(expanded_edges, src, dst)
                if not path_edges:
                    raise SystemExit(f"No path between {src} and {dst}")
                edge_params = {}
                for a, b, dist_m, orig in path_edges:
                    dist_km = dist_m / 1000.0
                    chosen_strategy = args.strategy if (args.strategy == "BK" or orig in upgrade_edges) else "BK"
                    p_eg, attempt_rate, coherence, p_bsm_edge, extra_lat = edge_params_for_strategy(
                        chosen_strategy, dist_km, args.eta, knobs
                    )
                    edge_params[tuple(sorted((a, b)))] = EdgeParams(
                        attempt_rate_hz=attempt_rate, p_eg=p_eg, coherence_time_s=coherence, extra_latency_s=extra_lat
                    )

                p_bsm, swap_lat = swap_params_for_strategy(args.strategy, knobs)
                chain_path = []
                for a, b, _, _ in path_edges:
                    if not chain_path:
                        chain_path.append(a)
                    chain_path.append(b)

                res = simulate_entanglement_service(
                    path=chain_path,
                    edge_params=edge_params,
                    swap_params=SwapParams(p_bsm=p_bsm, latency_s=swap_lat),
                    seed=s,
                    horizon_s=args.horizon_s,
                    tau_s=args.tau_s,
                    num_requests=args.num_requests if args.lambda_req is None else None,
                    lambda_req=args.lambda_req,
                    otp_data_rate_bps=args.otp_data_rate_bps,
                    otp_session_duration_s=args.otp_session_duration_s,
                    otp_directions=args.otp_directions,
                    key_bits_per_pair=kb,
                )
                availabilities.append(res["availability"])
                for idx, req in enumerate(res["requests"]):
                    writer.writerow(
                        [
                            s,
                            src,
                            dst,
                            idx,
                            req.t_arrival,
                            req.deadline,
                            req.served,
                            req.t_done if req.t_done is not None else "",
                            req.bits_needed,
                            req.bits_delivered,
                        ]
                    )
            f_raw.flush()

        availability_mean = float(sum(availabilities) / len(availabilities)) if availabilities else 0.0
        summary = {
            "availability_mean": availability_mean,
            "key_bits_per_pair": kb,
            "seeds": seeds,
            "pair_mode": args.pair_mode,
            "src_nodes": args.src_node,
            "dst_nodes": args.dst_node,
            "targets": {tgt: availability_mean >= tgt for tgt in (0.9, 0.99, 0.999)},
            "distance_dataset_id": args.distance_dataset_id,
            "upgrade_edges": sorted(list(upgrade_edges)),
            "strategy": args.strategy,
            "eta": args.eta,
        }
        summary_path.write_text(json.dumps(summary, indent=2))
        print(f"Wrote raw to {raw_path}")
        print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
