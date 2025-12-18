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
)
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def edge_usage_counts(topo):
    from collections import defaultdict, deque

    counts = defaultdict(int)
    nodes = list(topo.keys())
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            src, dst = nodes[i], nodes[j]
            q = deque([[src]])
            visited = {src}
            path = None
            while q:
                p = q.popleft()
                n = p[-1]
                if n == dst:
                    path = p
                    break
                for nei in topo[n]:
                    if nei not in visited:
                        visited.add(nei)
                        q.append(p + [nei])
            if not path:
                continue
            for k in range(len(path) - 1):
                edge = tuple(sorted((path[k], path[k + 1])))
                counts[edge] += 1
    return counts


def pick_upgrade_edges(topo, policy: str, k: int) -> List[Tuple[str, str]]:
    edges = [tuple(sorted(e)) for e in nsfnet_edges()]
    if k <= 0:
        return []
    if policy == "shortestpath_count":
        ranked = sorted(edge_usage_counts(topo).items(), key=lambda x: (-x[1], x[0]))
        return [e for e, _ in ranked[:k]]
    elif policy == "betweenness":
        # simple betweenness via shortest-path pair counting (same as above)
        ranked = sorted(edge_usage_counts(topo).items(), key=lambda x: (-x[1], x[0]))
        return [e for e, _ in ranked[:k]]
    return []


def make_edge_params(
    upgraded: List[Tuple[str, str]],
    attempt_rate_bk: float,
    p_eg_bk: float,
    attempt_rate_eqt: float,
    p_eg_eqt: float,
    coherence_bk: float,
    coherence_eqt: float,
    dist_map: Dict[Tuple[str, str], float],
    loss_db_per_km: float,
    override_bk_dist_map: bool = False,
) -> Dict[Tuple[str, str], EdgeParams]:
    edges = [tuple(sorted(e)) for e in nsfnet_edges()]
    params = {}
    for e in edges:
        dist_km = dist_map.get(e, 1000.0) / 1000.0 if dist_map else None
        if dist_km is not None and override_bk_dist_map:
            attn_db = loss_db_per_km * dist_km
            p_eg_bk_eff = math.exp(-attn_db * math.log(10) / 10.0)
        else:
            p_eg_bk_eff = p_eg_bk
        if e in upgraded:
            params[e] = EdgeParams(attempt_rate_eqt, p_eg_eqt, coherence_eqt)
        else:
            params[e] = EdgeParams(attempt_rate_bk, p_eg_bk_eff, coherence_bk)
    return params


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
    p.add_argument("--workers", type=int, default=1)
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

    topo = nsfnet_topology()
    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)

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
        "availability",
        "served",
        "total",
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

    def run_task(task):
        strat, load, kb, uk, seed = task
        upgraded = pick_upgrade_edges(topo, args.upgrade_policy, uk)
        edge_params = make_edge_params(
            upgraded,
            args.attempt_rate_bk,
            args.p_eg_bk,
            args.attempt_rate_eqt,
            args.p_eg_eqt,
            args.coherence_bk,
            args.coherence_eqt,
            dist_map,
            args.loss_db_per_km,
            override_bk_dist_map=True,
        )
        swap_params = SwapParams(args.p_bsm, 0.0)
        base_param = next(iter(edge_params.values()))
        chain_edges = {
            tuple(sorted(("A", "R1"))): base_param,
            tuple(sorted(("R1", "R2"))): base_param,
            tuple(sorted(("R2", "B"))): base_param,
        }
        res = simulate_entanglement_service(
            path=["A", "R1", "R2", "B"],
            edge_params=chain_edges,
            swap_params=swap_params,
            seed=seed,
            horizon_s=args.horizon_s,
            tau_s=args.tau_s,
            num_requests=args.num_requests,
            lambda_req=load,
            key_bits_per_pair=kb,
        )
        return (strat, load, kb, uk, seed, res["availability"], res["served"], res["total"])

    results = []
    max_workers = min(args.workers, 4)
    if args.workers > 4:
        print("Capping workers to 4")
    print(f"Using effective_workers={max_workers}")
    if max_workers > 1:
        try:
            with ProcessPoolExecutor(max_workers=max_workers) as ex:
                fut_map = {ex.submit(run_task, t): t for t in tasks}
                for fut in as_completed(fut_map):
                    row = fut.result()
                    writer.writerow(row)
                    f_raw.flush()
                    results.append(row)
        except PermissionError:
            for t in tasks:
                row = run_task(t)
                writer.writerow(row)
                f_raw.flush()
                results.append(row)
    else:
        for t in tasks:
            row = run_task(t)
            writer.writerow(row)
            f_raw.flush()
            results.append(row)
    f_raw.close()

    agg = defaultdict(list)
    for r in results:
        key = (r[0], r[1], r[2], r[3])
        agg[key].append(r[5])
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
