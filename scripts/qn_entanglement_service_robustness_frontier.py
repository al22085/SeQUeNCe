"""Robustness frontier across multiple pairs/etas/upgrades for entanglement-service."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    nsfnet_topology,
    load_distance_dataset,
    load_edge_distances_csv,
    subdivide_edges,
    shortest_path_edges,
    pick_upgrade_edges,
)
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def parse_pairs(raw: str) -> List[Tuple[str, str]]:
    return [tuple(p.split("-")) for p in raw.split(",") if p]


def parse_args():
    p = argparse.ArgumentParser(description="Robustness frontier across pairs/seeds/upgrades.")
    p.add_argument("--pairs-csv", type=Path, default=None, help="CSV from qn_select_nsfnet_pairs.py")
    p.add_argument("--pairs", type=str, default="", help="Comma list like 1-2,3-7")
    p.add_argument("--etas", type=str, default="0.5,0.9")
    p.add_argument("--upgrade-k-list", type=str, default="0,3,7,21")
    p.add_argument("--strategies", type=str, default="BK,EQT")
    p.add_argument("--targets", type=str, default="0.9,0.99,0.999")
    p.add_argument("--kbits-list", type=str, default="0.5,1.0")
    p.add_argument("--key-bits-per-pair-list", type=str, default=None, help="Alias for kbits-list.")
    p.add_argument("--seeds", type=str, default="0,1,2,3")
    p.add_argument("--load-grid", type=str, default="0.5,1.0,2.0,5.0")
    p.add_argument("--binary-search", action="store_true", help="Enable binary search on load instead of fixed grid.")
    p.add_argument("--load-min", type=float, default=0.001)
    p.add_argument("--load-max", type=float, default=2.0)
    p.add_argument("--load-tol", type=float, default=0.05)
    p.add_argument("--horizon-s", type=float, default=0.5)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=10000)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=20000)
    p.add_argument("--coherence-opt-s", type=float, default=0.05)
    p.add_argument("--coherence-sc-s", type=float, default=0.05)
    p.add_argument("--eta", type=float, default=0.8, help="Unused (compat)")
    p.add_argument("--p-bsm-opt", type=float, default=0.9)
    p.add_argument("--p-bsm-sc", type=float, default=0.95)
    p.add_argument("--loss-db-per-km", type=float, default=0.2)
    p.add_argument("--transduction-latency-s", type=float, default=0.0)
    p.add_argument("--swap-latency-s", type=float, default=0.0)
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--network-scope", choices=["shortest_path", "full"], default="shortest_path", help="Restrict to shortest-path chain for efficiency.")
    p.add_argument("--edge-distance-csv", type=Path, default=None)
    p.add_argument(
        "--distance-dataset-id",
        type=str,
        default="topologybench_nsfnet13",
        help="Distance dataset id (sndlib_great_circle_heuristic | topologybench_nsfnet13)",
    )
    p.add_argument("--otp-data-rate-bps", type=float, default=1000.0)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--swap-schedule", choices=["sequential", "balanced"], default="sequential")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_entanglement_service_robustness"))
    return p.parse_args()


def main():
    args = parse_args()
    pairs: List[Tuple[str, str]] = []
    if args.pairs_csv:
        with args.pairs_csv.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                pairs.append((row["src"], row["dst"]))
    if args.pairs:
        pairs.extend(parse_pairs(args.pairs))
    if not pairs:
        raise SystemExit("No pairs provided; supply --pairs-csv or --pairs")

    etas = parse_list(args.etas, float)
    upgrade_ks = parse_list(args.upgrade_k_list, int)
    strategies = parse_list(args.strategies, str)
    targets = parse_list(args.targets, float)
    kbits_raw = args.key_bits_per_pair_list if args.key_bits_per_pair_list else args.kbits_list
    kbits_list = parse_list(kbits_raw, float)
    seeds = parse_list(args.seeds, int)
    load_grid = parse_list(args.load_grid, float)

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

    topo = nsfnet_topology()
    upgrade_edges_cache = {uk: set(pick_upgrade_edges(topo, "shortestpath_count", uk)) for uk in upgrade_ks}

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "robust_frontier_raw.csv"
    pair_path = out_dir / "robust_frontier_pairs.csv"
    agg_path = out_dir / "robust_frontier_agg.csv"

    raw_headers = [
        "pair",
        "eta",
        "strategy",
        "upgrade_k",
        "kbits",
        "load",
        "availability_mean",
        "availability_std",
        "runs",
    ]

    tasks = []
    for pair in pairs:
        if args.network_scope == "shortest_path":
            path_edges = shortest_path_edges(expanded_edges, pair[0], pair[1])
        else:
            path_edges = expanded_edges
        if not path_edges:
            continue
        for eta_val in etas:
            for uk in upgrade_ks:
                for strat in strategies:
                    for kb in kbits_list:
                        tasks.append((pair, path_edges, eta_val, uk, strat, kb))

    def eval_task(task):
        pair, path_edges, eta_val, uk, strat, kb = task
        upgraded_edges = upgrade_edges_cache[uk]
        p_bsm, swap_lat = swap_params_for_strategy(strat, knobs)
        def evaluate_load(load: float) -> float:
            avails = []
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
                    key_bits_per_pair=kb,
                    swap_schedule=args.swap_schedule,
                )
                avails.append(res["availability"])
            return float(np.mean(avails)) if avails else 0.0, float(np.std(avails, ddof=0)) if avails else 0.0

        load_rows = []
        frontier_rows = []
        evaluated = set()

        def record(load, mean_av, std_av):
            load_rows.append((load, mean_av, std_av, len(seeds)))
            evaluated.add(load)

        if args.binary_search:
            for tgt in targets:
                low = args.load_min
                high = args.load_max
                # evaluate bounds
                if low not in evaluated:
                    m, s = evaluate_load(low)
                    record(low, m, s)
                else:
                    m, s = next((mn, st) for l, mn, st, _ in load_rows if l == low)
                if high not in evaluated:
                    mh, sh = evaluate_load(high)
                    record(high, mh, sh)
                else:
                    mh, sh = next((mn, st) for l, mn, st, _ in load_rows if l == high)
                frontier = 0.0
                if m < tgt:
                    frontier = 0.0
                elif mh >= tgt:
                    frontier = high
                else:
                    while high - low > args.load_tol:
                        mid = (low + high) / 2.0
                        mm, sm = evaluate_load(mid)
                        record(mid, mm, sm)
                        if mm >= tgt:
                            low = mid
                        else:
                            high = mid
                    frontier = low
                frontier_rows.append(
                    {
                        "pair": f"{pair[0]}-{pair[1]}",
                        "eta": eta_val,
                        "strategy": strat,
                        "upgrade_k": uk,
                        "kbits": kb,
                        "target": tgt,
                        "frontier_load": frontier,
                    }
                )
        else:
            for load in load_grid:
                m, s = evaluate_load(load)
                record(load, m, s)
            for tgt in targets:
                frontier = 0.0
                for load, mean_av, _, _ in load_rows:
                    if mean_av >= tgt and load > frontier:
                        frontier = load
                frontier_rows.append(
                    {
                        "pair": f"{pair[0]}-{pair[1]}",
                        "eta": eta_val,
                        "strategy": strat,
                        "upgrade_k": uk,
                        "kbits": kb,
                        "target": tgt,
                        "frontier_load": frontier,
                    }
                )
        return pair, eta_val, strat, uk, kb, load_rows, frontier_rows

    max_workers = min(max(1, args.workers), 4)
    print(f"Using effective_workers={max_workers}")
    results = []
    if max_workers > 1:
        try:
            with ProcessPoolExecutor(max_workers=max_workers) as ex:
                fut_map = {ex.submit(eval_task, t): t for t in tasks}
                for fut in as_completed(fut_map):
                    results.append(fut.result())
        except PermissionError:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                fut_map = {ex.submit(eval_task, t): t for t in tasks}
                for fut in as_completed(fut_map):
                    results.append(fut.result())
    else:
        for t in tasks:
            results.append(eval_task(t))

    # write raw (load-level) and pair-level frontier
    with raw_path.open("w", newline="") as f_raw:
        writer = csv.writer(f_raw)
        writer.writerow(raw_headers)
        for pair, eta_val, strat, uk, kb, load_rows, frontier_rows in results:
            for load, mean_av, std_av, runs in load_rows:
                writer.writerow([
                    f"{pair[0]}-{pair[1]}",
                    eta_val,
                    strat,
                    uk,
                    kb,
                    load,
                    mean_av,
                    std_av,
                    runs,
                ])

    pair_rows = []
    for _, _, _, _, _, _, frontier_rows in results:
        pair_rows.extend(frontier_rows)
    with pair_path.open("w", newline="") as f_pair:
        writer = csv.DictWriter(
            f_pair,
            fieldnames=["pair", "eta", "strategy", "upgrade_k", "kbits", "target", "frontier_load"],
        )
        writer.writeheader()
        writer.writerows(pair_rows)

    # aggregate across pairs
    agg_rows = []
    for eta_val in etas:
        for strat in strategies:
            for uk in upgrade_ks:
                for kb in kbits_list:
                    for tgt in targets:
                        vals = [
                            float(r["frontier_load"])
                            for r in pair_rows
                            if float(r["eta"]) == eta_val
                            and r["strategy"] == strat
                            and int(r["upgrade_k"]) == uk
                            and float(r["kbits"]) == kb
                            and float(r["target"]) == tgt
                        ]
                        if not vals:
                            continue
                        agg_rows.append(
                            {
                                "eta": eta_val,
                                "strategy": strat,
                                "upgrade_k": uk,
                                "kbits": kb,
                                "target": tgt,
                                "frontier_median": float(np.median(vals)),
                                "frontier_mean": float(np.mean(vals)),
                                "frontier_min": float(np.min(vals)),
                                "frontier_max": float(np.max(vals)),
                                "pairs": len(vals),
                            }
                        )

    with agg_path.open("w", newline="") as f_agg:
        writer = csv.DictWriter(
            f_agg,
            fieldnames=
            [
                "eta",
                "strategy",
                "upgrade_k",
                "kbits",
                "target",
                "frontier_median",
                "frontier_mean",
                "frontier_min",
                "frontier_max",
                "pairs",
            ],
        )
        writer.writeheader()
        writer.writerows(agg_rows)

    print(f"Wrote raw to {raw_path}")
    print(f"Wrote pair frontiers to {pair_path}")
    print(f"Wrote agg to {agg_path}")


if __name__ == "__main__":
    main()
