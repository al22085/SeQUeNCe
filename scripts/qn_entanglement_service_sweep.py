"""Sweep entanglement-service availability vs offered load on NSFNET."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    nsfnet_edges,
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


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def ci95(std: float, n: int) -> float:
    if n <= 0:
        return 0.0
    return 1.96 * std / math.sqrt(n)


def parse_args():
    p = argparse.ArgumentParser(description="Sweep entanglement-service availability vs load on NSFNET.")
    p.add_argument("--strategies", default="BK,EQT")
    p.add_argument("--loads", default="0.5,1.0", help="Comma list of lambda_req (requests/s).")
    p.add_argument("--seeds", default="0,1")
    p.add_argument("--num-requests", type=int, default=30)
    p.add_argument("--horizon-s", type=float, default=0.2)
    p.add_argument("--tau-s", type=float, default=0.05)
    p.add_argument("--key-bits-per-pair-list", type=str, default="0.5,1.0")
    p.add_argument("--targets", type=str, default="0.9,0.99,0.999")
    p.add_argument("--attempt-rate-bk", type=float, default=1e5)
    p.add_argument("--attempt-rate-eqt", type=float, default=1e5)
    p.add_argument("--p-eg-bk", type=float, default=0.2)
    p.add_argument("--p-eg-eqt", type=float, default=0.3)
    p.add_argument("--coherence-bk", type=float, default=0.02)
    p.add_argument("--coherence-eqt", type=float, default=0.03)
    p.add_argument("--p-bsm", type=float, default=0.9)
    p.add_argument("--eta", type=float, default=0.8)
    p.add_argument("--p-bsm-opt", type=float, default=0.9)
    p.add_argument("--p-bsm-sc", type=float, default=0.95)
    p.add_argument("--coherence-opt-s", type=float, default=0.02)
    p.add_argument("--coherence-sc-s", type=float, default=0.03)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=1e3)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=1e3)
    p.add_argument("--transduction-latency-s", type=float, default=0.0)
    p.add_argument("--swap-latency-s", type=float, default=0.0)
    p.add_argument("--edge-distance-csv", type=Path, default=None)
    p.add_argument("--loss-db-per-km", type=float, default=0.2)
    p.add_argument(
        "--distance-dataset-id",
        type=str,
        default="sndlib_great_circle_heuristic",
        help="Distance dataset id (sndlib_great_circle_heuristic | topologybench_nsfnet13)",
    )
    p.add_argument("--upgrade-k-list", type=str, default="0", help="Comma list of edge counts to upgrade.")
    p.add_argument("--upgrade-policy", choices=["shortestpath_count", "betweenness"], default="shortestpath_count")
    p.add_argument("--upgrade-mode", choices=["edges", "repeaters"], default="edges")
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--pair-mode", choices=["fixed", "random"], default="fixed")
    p.add_argument("--src-node", type=str, default="1")
    p.add_argument("--dst-node", type=str, default="14")
    p.add_argument("--otp-data-rate-bps", type=float, default=1e3)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_entanglement_service_sweep"))
    p.add_argument("--resume", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    strategies = parse_list(args.strategies, str)
    loads = parse_list(args.loads, float)
    seeds = parse_list(args.seeds, int)
    kbits_list = parse_list(args.key_bits_per_pair_list, float)
    targets = parse_list(args.targets, float)
    upgrade_k_list = parse_list(args.upgrade_k_list, int)
    if args.upgrade_mode != "edges":
        raise SystemExit("upgrade-mode repeaters not implemented; use edges")

    topo = nsfnet_topology()
    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
    expanded_edges, mapping, virtual_nodes = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
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

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "ent_sweep_raw.csv"
    agg_path = out_dir / "ent_sweep_agg.csv"
    raw_headers = [
        "strategy",
        "lambda",
        "seed",
        "kbits",
        "upgrade_k",
        "eta",
        "distance_dataset_id",
        "upgrade_edges",
        "src",
        "dst",
        "availability",
        "served",
        "total",
        "bits_requested",
        "bits_delivered",
    ]
    mode = "a" if (args.resume and raw_path.exists()) else "w"
    f_raw = raw_path.open(mode, newline="")
    writer = csv.writer(f_raw)
    if mode == "w":
        writer.writerow(raw_headers)

    tasks = []
    for strat in strategies:
        for load in loads:
            for kb in kbits_list:
                for uk in upgrade_k_list:
                    for seed in seeds:
                        tasks.append((strat, load, kb, uk, seed))

    def choose_pair(seed: int):
        if args.pair_mode == "fixed":
            return args.src_node, args.dst_node
        rng = np.random.default_rng(seed)
        candidates = sorted(set(expanded_nodes(expanded_edges)))
        if len(candidates) < 2:
            return args.src_node, args.dst_node
        src_idx = rng.integers(0, len(candidates))
        dst_idx = rng.integers(0, len(candidates) - 1)
        if dst_idx >= src_idx:
            dst_idx += 1
        return candidates[src_idx], candidates[dst_idx]

    def run_task(task):
        strat, load, kb, uk, seed = task
        upgraded = pick_upgrade_edges(topo, args.upgrade_policy, uk)
        src, dst = choose_pair(seed)
        path_edges = shortest_path_edges(expanded_edges, src, dst)
        edge_params = {}
        for a, b, dist_m, orig in path_edges:
            dist_km = dist_m / 1000.0
            use_strat = strat
            if strat == "BK":
                use_strat = "BK"
            else:
                use_strat = "EQT" if orig in upgraded else "BK"
            p_eg, attempt_rate, coherence, p_bsm_seg, extra_lat = edge_params_for_strategy(use_strat, dist_km, args.eta, knobs)
            edge_params[tuple(sorted((a, b)))] = EdgeParams(attempt_rate, p_eg, coherence, extra_lat)

        if strat == "BK":
            p_bsm, swap_lat = swap_params_for_strategy("BK", knobs)
        else:
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
                num_requests=args.num_requests,
                lambda_req=load,
                key_bits_per_pair=kb,
                otp_data_rate_bps=args.otp_data_rate_bps,
                otp_session_duration_s=args.otp_session_duration_s,
                otp_directions=args.otp_directions,
            )
        return (
            strat,
            load,
            kb,
            uk,
            seed,
            upgraded,
            src,
            dst,
            res["availability"],
            res["served"],
            res["total"],
            res["bits_requested"],
            res["bits_delivered"],
        )

    if args.workers < 2 or args.workers > 10:
        raise SystemExit("workers must be between 2 and 10")
    results = []
    max_workers = min(args.workers, 10)
    print(f"Using effective_workers={max_workers}")
    with ProcessPoolExecutor(max_workers=max_workers) as ex:
        fut_map = {ex.submit(run_task, t): t for t in tasks}
        for fut in as_completed(fut_map):
            row = fut.result()
            writer.writerow(
                [
                    row[0],
                    row[1],
                    row[4],
                    row[2],
                    row[3],
                    args.eta,
                    args.distance_dataset_id,
                    ";".join("-".join(e) for e in sorted(row[5])),
                    row[6],
                    row[7],
                    row[8],
                    row[9],
                    row[10],
                    row[11],
                    row[12],
                ]
            )
            f_raw.flush()
            results.append(row)
    f_raw.close()

    agg = defaultdict(list)
    for r in results:
        key = (r[0], r[1], r[2], r[3])
        agg[key].append(r[8])
    agg_headers = [
        "strategy",
        "lambda",
        "kbits",
        "upgrade_k",
        "availability_mean",
        "availability_std",
        "availability_ci95",
        "runs",
    ]
    agg_rows = []
    for key, vals in agg.items():
        mean = float(np.mean(vals)) if vals else 0.0
        std = float(np.std(vals, ddof=0)) if vals else 0.0
        agg_rows.append((key[0], key[1], key[2], key[3], mean, std, ci95(std, len(vals)), len(vals)))
    with agg_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(agg_headers)
        w.writerows(agg_rows)
    print(f"Wrote raw to {raw_path}")
    print(f"Wrote agg to {agg_path}")


if __name__ == "__main__":
    main()
