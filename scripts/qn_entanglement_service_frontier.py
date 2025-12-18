"""Frontier: max offered load achieving SLA targets for entanglement-service on NSFNET."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    nsfnet_topology,
    nsfnet_edges,
    load_distance_dataset,
    load_edge_distances_csv,
)
from scripts.qn_entanglement_service_sweep import (
    pick_upgrade_edges,
    make_edge_params,
    ci95,
)
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy
from sequence.qn.entanglement_service import SwapParams, simulate_entanglement_service


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def parse_args():
    p = argparse.ArgumentParser(description="Entanglement service SLA frontier (max load) for NSFNET.")
    p.add_argument("--strategies", default="BK,EQT")
    p.add_argument("--targets", default="0.9,0.99,0.999")
    p.add_argument("--kbits-list", default="0.5,1.0")
    p.add_argument("--load-min", type=float, default=0.1)
    p.add_argument("--load-max", type=float, default=5.0)
    p.add_argument("--load-tol", type=float, default=0.1)
    p.add_argument("--seeds", default="0,1")
    p.add_argument("--num-requests", type=int, default=40)
    p.add_argument("--horizon-s", type=float, default=0.3)
    p.add_argument("--tau-s", type=float, default=0.05)
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
    p.add_argument("--attempt-rate-opt-hz", type=float, default=1e5)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=1e5)
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
    p.add_argument("--upgrade-k-list", type=str, default="0")
    p.add_argument("--upgrade-policy", choices=["shortestpath_count", "betweenness"], default="shortestpath_count")
    p.add_argument("--upgrade-mode", choices=["edges", "repeaters"], default="edges")
    p.add_argument("--workers", type=int, default=1)
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_entanglement_service_frontier"))
    p.add_argument("--resume", action="store_true")
    return p.parse_args()


def main():
    args = parse_args()
    strategies = parse_list(args.strategies, str)
    targets = parse_list(args.targets, float)
    kbits_list = parse_list(args.kbits_list, float)
    seeds = parse_list(args.seeds, int)
    upgrade_k_list = parse_list(args.upgrade_k_list, int)
    if args.upgrade_mode != "edges":
        raise SystemExit("upgrade-mode repeaters not implemented; use edges")

    topo = nsfnet_topology()
    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
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
    raw_path = out_dir / "ent_frontier_raw.csv"
    agg_path = out_dir / "ent_frontier_agg.csv"
    raw_headers = [
        "strategy",
        "target",
        "kbits",
        "upgrade_k",
        "eta",
        "distance_dataset_id",
        "upgrade_edges",
        "load",
        "availability_mean",
        "availability_std",
        "runs",
    ]
    mode = "a" if (args.resume and raw_path.exists()) else "w"
    f_raw = raw_path.open(mode, newline="")
    writer = csv.writer(f_raw)
    if mode == "w":
        writer.writerow(raw_headers)

    def eval_load(strategy, load, kb, uk, target_val):
        upgraded = pick_upgrade_edges(topo, args.upgrade_policy, uk)
        edge_params = make_edge_params(upgraded, args.eta, knobs, dist_map)
        p_bsm, swap_lat = swap_params_for_strategy(strategy, knobs)
        if upgraded:
            rep_edges = [edge_params[e] for e in edge_params if e in upgraded]
        else:
            rep_edges = [edge_params[e] for e in edge_params]
        base_param = rep_edges[0]
        chain_edges = {
            tuple(sorted(("A", "R1"))): base_param,
            tuple(sorted(("R1", "R2"))): base_param,
            tuple(sorted(("R2", "B"))): base_param,
        }
        avails = []
        for seed in seeds:
            res = simulate_entanglement_service(
                path=["A", "R1", "R2", "B"],
                edge_params=chain_edges,
                swap_params=SwapParams(p_bsm=p_bsm, latency_s=swap_lat),
                seed=seed,
                horizon_s=args.horizon_s,
                tau_s=args.tau_s,
                num_requests=args.num_requests,
                lambda_req=load,
                key_bits_per_pair=kb,
            )
            avails.append(res["availability"])
        mean = float(np.mean(avails)) if avails else 0.0
        std = float(np.std(avails, ddof=0)) if avails else 0.0
        writer.writerow(
            [
                strategy,
                target_val,
                kb,
                uk,
                args.eta,
                args.distance_dataset_id,
                ";".join("-".join(e) for e in sorted(upgraded)),
                load,
                mean,
                std,
                len(avails),
            ]
        )
        f_raw.flush()
        return mean, std

    def frontier_for(strategy, target, kb, uk):
        lo, hi = args.load_min, args.load_max
        alo, _ = eval_load(strategy, lo, kb, uk, target)
        ahi, _ = eval_load(strategy, hi, kb, uk, target)
        if ahi < target:
            return lo, ahi, 2
        evals = 2
        while hi - lo > args.load_tol:
            mid = (lo + hi) / 2
            amid, _ = eval_load(strategy, mid, kb, uk, target)
            evals += 1
            if amid >= target:
                lo, alo = mid, amid
            else:
                hi, ahi = mid, amid
        return lo, alo, evals

    results = []
    tasks = []
    for strat in strategies:
        for kb in kbits_list:
            for uk in upgrade_k_list:
                for tgt in targets:
                    tasks.append((strat, kb, uk, tgt))

    max_workers = min(args.workers, 4)
    if args.workers > 4:
        print("Capping workers to 4")
    print(f"Using effective_workers={max_workers}")

    def run_task(task):
        strat, kb, uk, tgt = task
        frontier, avail, evals = frontier_for(strat, tgt, kb, uk)
        return strat, tgt, kb, uk, frontier, avail, evals

    if max_workers > 1:
        try:
            with ProcessPoolExecutor(max_workers=max_workers) as ex:
                fut_map = {ex.submit(run_task, t): t for t in tasks}
                for fut in as_completed(fut_map):
                    results.append(fut.result())
        except PermissionError:
            for t in tasks:
                results.append(run_task(t))
    else:
        for t in tasks:
            results.append(run_task(t))

    agg_headers = [
        "strategy",
        "target",
        "kbits",
        "upgrade_k",
        "frontier_load",
        "availability_at_frontier",
        "eval_count",
    ]
    with agg_path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(agg_headers)
        for r in results:
            w.writerow(r)
    f_raw.close()
    print(f"Wrote raw to {raw_path}")
    print(f"Wrote agg to {agg_path}")


if __name__ == "__main__":
    main()
