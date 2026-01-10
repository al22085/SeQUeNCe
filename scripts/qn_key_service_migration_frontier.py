"""Compute migration frontier (max OTP rate achieving target availability) for key-service."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
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

from scripts.qn_experiment_presets import apply_preset
from scripts.qn_topologies import nsfnet_topology, nsfnet_edges
from sequence.qn.key_service import compute_link_key_rate, simulate_key_service
from sequence.qn.parallel import normalize_workers


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def load_link_rates(args: argparse.Namespace) -> Dict[Tuple[str, str], float]:
    rates = {}
    if args.link_rate_json:
        for path in args.link_rate_json:
            data = json.loads(Path(path).read_text())
            for k, v in data.items():
                a, b = k.split("-")
                rates[(a, b)] = float(v)
    if args.link_rate_csv:
        for path in args.link_rate_csv:
            with Path(path).open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    edge = row.get("edge") or row.get("link")
                    if not edge:
                        continue
                    a, b = edge.split("-")
                    rates[(a, b)] = float(row["rate_bps"])
    return rates


def edge_usage_counts(topo):
    # simple all-pairs shortest paths counting
    nodes = list(topo.keys())
    counts = defaultdict(int)
    from collections import deque

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


def apply_upgrades(base_rates: Dict[Tuple[str, str], float], topo, args: argparse.Namespace):
    scenarios = {"baseline": base_rates}
    counts = edge_usage_counts(topo)

    def upgrade_edges(name, edges, mult):
        r = base_rates.copy()
        for e in edges:
            if e in r:
                r[e] *= mult
        scenarios[name] = r

    if args.upgrade_topk and args.upgrade_mult:
        ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        chosen = [edge for edge, _ in ranked[: args.upgrade_topk]]
        upgrade_edges(f"topk{args.upgrade_topk}x{args.upgrade_mult}", chosen, args.upgrade_mult)
    if args.upgrade_edges and args.upgrade_mult:
        edges_list = []
        for item in args.upgrade_edges.split(","):
            if not item:
                continue
            a, b = item.split("-")
            edges_list.append(tuple(sorted((a, b))))
        upgrade_edges(f"edgesx{args.upgrade_mult}", edges_list, args.upgrade_mult)

    # explicit link maps as separate scenarios
    if args.link_rate_json or args.link_rate_csv:
        ext = load_link_rates(args)
        if ext:
            scenarios["linkmap"] = ext
    return scenarios


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Key-service migration frontier at target availability.")
    p.add_argument("--topology", choices=["nsfnet"], default="nsfnet")
    p.add_argument("--strategies", default="BK,DQT,EQT")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--seeds", default="", help="Optional list to override single seed.")
    p.add_argument("--horizon-s", type=float, default=1.0)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--lambdas", default="1.0,5.0")
    p.add_argument("--target-availability", type=float, default=0.999)
    p.add_argument("--targets", type=str, default="0.9,0.99,0.999", help="Comma list of target availability levels.")
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--session-key-bits", type=int, default=1024)
    p.add_argument("--kmax-bits", type=float, default=1e5)
    p.add_argument("--kmax-list", default="")
    p.add_argument("--otp-rate-min-bps", type=float, default=1e3)
    p.add_argument("--otp-rate-max-bps", type=float, default=1e6)
    p.add_argument("--rate-steps", type=int, default=10)
    p.add_argument("--binary-search", action="store_true", help="Use binary search instead of grid.")
    p.add_argument("--rate-tol-bps", type=float, default=1e3)
    p.add_argument("--base-key-rate-bps", type=float, default=1e5)
    p.add_argument("--strategy-params", type=json.loads, default="{}", help="JSON dict")
    p.add_argument("--link-rate-json", action="append", help="Edge->rate_bps JSON (edge as 'A-B')", default=[])
    p.add_argument("--link-rate-csv", action="append", help="CSV edge,rate_bps", default=[])
    p.add_argument("--upgrade-topk", type=int, default=0)
    p.add_argument("--upgrade-mult", type=float, default=None)
    p.add_argument("--upgrade-edges", type=str, default="")
    p.add_argument("--preset", type=str, default="", help="Named preset.")
    p.add_argument("--workers", type=int, default=2, help="Parallel workers (2..20).")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_key_service_frontier"))
    p.add_argument("--resume", action="store_true")
    p.add_argument("--base-seed", type=int, default=0)
    return p.parse_args()


def main():
    args = parse_args()
    args = apply_preset(args, args.preset)
    strategies = parse_list(args.strategies, str)
    lambdas = parse_list(args.lambdas, float)
    kmax_list = parse_list(args.kmax_list, float) if args.kmax_list else [args.kmax_bits]
    seeds = parse_list(args.seeds, int) if args.seeds else [args.seed]
    targets_arg = args.targets.strip() if args.targets is not None else ""
    targets = parse_list(targets_arg, float) if targets_arg else []
    if not targets:
        targets = [args.target_availability]
    topo = nsfnet_topology()
    edges = [tuple(sorted(e)) for e in nsfnet_edges()]

    # enforce worker policy: non-trivial runs need >=2 unless single cell
    total_cells = len(strategies) * len(lambdas) * len(kmax_list) * len(targets)
    if total_cells > 1 and args.workers < 2:
        raise ValueError("Workers must be >=2 for non-trivial frontier runs")
    try:
        effective_workers, cpu_limit, cpu_reason = normalize_workers(args.workers, min_workers=2, max_workers=20)
    except RuntimeError as exc:
        raise ValueError(str(exc)) from exc
    if cpu_limit is not None and effective_workers < args.workers:
        print(f"WARNING: cpu_limit={cpu_limit:.2f} ({cpu_reason}); effective_workers={effective_workers}")
    args.workers = effective_workers

    base_rates = {e: compute_link_key_rate("BK", {}, args.strategy_params, args.base_key_rate_bps) for e in edges}
    scenarios = apply_upgrades(base_rates, topo, args)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "frontier_raw.csv"
    agg_path = out_dir / "frontier_agg.csv"
    summary_path = out_dir / "summary.json"

    evaluated = set()
    eval_cache = {}
    base_eval_cache = {}
    if args.resume and raw_path.exists():
        with raw_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                evaluated.add(
                    (
                        row["scenario"],
                        row["strategy"],
                        float(row["lambda"]),
                        float(row["kmax"]),
                        float(row.get("target_A", args.target_availability)),
                        float(row["otp_rate_bps"]),
                    )
                )
                key = (
                    row["scenario"],
                    row["strategy"],
                    float(row["lambda"]),
                    float(row["kmax"]),
                    float(row.get("target_A", args.target_availability)),
                    float(row["otp_rate_bps"]),
                )
                eval_cache[key] = (
                    float(row["availability"]),
                    int(row.get("served", 0)),
                    int(row.get("total", 0)),
                )
                base_key = (
                    row["scenario"],
                    row["strategy"],
                    float(row["lambda"]),
                    float(row["kmax"]),
                    float(row["otp_rate_bps"]),
                )
                base_eval_cache[base_key] = (
                    float(row["availability"]),
                    int(row.get("served", 0)),
                    int(row.get("total", 0)),
                )
    raw_headers = [
        "scenario",
        "strategy",
        "lambda",
        "kmax",
        "otp_rate_bps",
        "availability",
        "block_prob",
        "served",
        "total",
        "seeds",
        "target_A",
    ]
    mode = "a" if (args.resume and raw_path.exists()) else "w"
    f_raw = raw_path.open(mode, newline="")
    writer = csv.writer(f_raw)
    if mode == "w":
        writer.writerow(raw_headers)

    topo_id = f"nsfnet-{len(edges)}"

    def cell_seed(scenario: str, strategy: str, lamb: float, kmax: float, seed: int):
        key = f"{scenario}:{strategy}:{lamb}:{kmax}:{seed}:{args.base_seed}:{topo_id}"
        return args.base_seed + int.from_bytes(hashlib.md5(key.encode()).digest()[:8], "big") % (2**31)

    evaluated_keys = set(evaluated)

    def search_task(task):
        scenario_name, link_rates, strategy, lamb, kmax, target_A = task
        local_eval = dict(eval_cache)
        local_base = dict(base_eval_cache)
        new_rows = []

        def eval_rate(otp_rate):
            cache_key = (scenario_name, strategy, lamb, kmax, target_A, otp_rate)
            base_key = (scenario_name, strategy, lamb, kmax, otp_rate)
            if cache_key in local_eval:
                return local_eval[cache_key]
            if base_key in local_base:
                availability, served_sum, total_sum = local_base[base_key]
                local_eval[cache_key] = (availability, served_sum, total_sum)
                # ensure per-target raw row exists even if reused from base cache
                new_rows.append(
                    [scenario_name, strategy, lamb, kmax, otp_rate, availability, 1 - availability, served_sum, total_sum, len(seeds), target_A]
                )
                return availability, served_sum, total_sum
            served_sum = 0
            total_sum = 0
            for seed in seeds:
                res = simulate_key_service(
                    topo,
                    strategy=strategy,
                    seed=cell_seed(scenario_name, strategy, lamb, kmax, seed),
                    horizon_s=args.horizon_s,
                    lambda_req=lamb,
                    tau_s=args.tau_s,
                    crypto_model="otp",
                    otp_data_rate_bps=otp_rate,
                    otp_session_duration_s=args.otp_session_duration_s,
                    session_key_bits=args.session_key_bits,
                    kmax_bits=kmax,
                    base_key_rate_bps=args.base_key_rate_bps,
                    strategy_params=args.strategy_params,
                    routing="shortest",
                    allow_wait=True,
                    reserve_mode="upfront",
                    link_rates=link_rates,
                    otp_directions=args.otp_directions,
                )
                served_sum += res["served"]
                total_sum += res["total"]
            availability = served_sum / total_sum if total_sum else 0.0
            block = 1 - availability
            local_eval[cache_key] = (availability, served_sum, total_sum)
            local_base[base_key] = (availability, served_sum, total_sum)
            new_rows.append(
                [scenario_name, strategy, lamb, kmax, otp_rate, availability, block, served_sum, total_sum, len(seeds), target_A]
            )
            return availability, served_sum, total_sum

        low = args.otp_rate_min_bps
        high = args.otp_rate_max_bps
        target = target_A

        a_low, _, _ = eval_rate(low)
        a_high, _, _ = eval_rate(high)

        frontier = low
        avail_at_frontier = a_low
        if a_high >= target:
            frontier = high
            avail_at_frontier = a_high
        elif a_low < target and a_high < target:
            frontier = low
            avail_at_frontier = a_low
        else:
            lo, hi = low, high
            alo, ahi = a_low, a_high
            while hi - lo > args.rate_tol_bps:
                mid = (lo + hi) / 2
                amid, _, _ = eval_rate(mid)
                if amid >= target:
                    lo, alo = mid, amid
                else:
                    hi, ahi = mid, amid
            frontier = lo
            avail_at_frontier = alo
        offered = lamb * args.otp_session_duration_s * args.otp_directions * frontier
        return (scenario_name, strategy, lamb, kmax, target_A, frontier, avail_at_frontier, offered), new_rows

    tasks = []
    for scenario_name, rates in scenarios.items():
        for strat in strategies:
            for lamb in lambdas:
                for kmax in kmax_list:
                    for target_A in targets:
                        tasks.append((scenario_name, rates, strat, lamb, kmax, target_A))

    max_workers = args.workers
    print(f"Using pool_kind=process effective_workers={max_workers} task_count={len(tasks)} chunksize=1")

    results = []

    def write_rows(rows):
        for row in rows:
            key = (row[0], row[1], float(row[2]), float(row[3]), float(row[10]), float(row[4]))
            if key in evaluated_keys:
                continue
            writer.writerow(row)
            f_raw.flush()
            evaluated_keys.add(key)
            eval_cache[key] = (float(row[5]), int(row[7]), int(row[8]))
            base_key = (row[0], row[1], float(row[2]), float(row[3]), float(row[4]))
            base_eval_cache[base_key] = (float(row[5]), int(row[7]), int(row[8]))

    if tasks:
        with ProcessPoolExecutor(max_workers=max_workers) as ex:
            fut_map = {ex.submit(search_task, t): t for t in tasks}
            for fut in as_completed(fut_map):
                res, rows = fut.result()
                write_rows(rows)
                results.append(res)

    # monotone envelope per (scenario,strategy,kmax)
    grouped = defaultdict(list)
    for r in results:
        grouped[(r[0], r[1], r[3], r[4])].append(r)  # scenario,strategy,kmax,target
    mono_rows = []
    for key, vals in grouped.items():
        vals.sort(key=lambda x: x[2])  # by lambda
        prev = None
        for v in vals:
            raw_frontier = v[5]
            if prev is None:
                mono = raw_frontier
            else:
                mono = min(raw_frontier, prev)
            prev = mono
            offered_mono = v[2] * args.otp_session_duration_s * args.otp_directions * mono
            mono_rows.append(
                [
                    v[0],  # scenario
                    v[1],  # strategy
                    v[2],  # lambda
                    v[3],  # kmax
                    v[4],  # target_A
                    raw_frontier,
                    mono,
                    v[6],  # availability_at_frontier
                    offered_mono,
                ]
            )
    agg_headers = [
        "scenario",
        "strategy",
        "lambda",
        "kmax",
        "target_A",
        "frontier_rate_bps_raw",
        "frontier_rate_bps",
        "availability_at_frontier",
        "offered_load_bps",
    ]
    with agg_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(agg_headers)
        writer.writerows(mono_rows)
    summary = {
        "targets": targets,
        "target_availability": args.target_availability,
        "otp_directions": args.otp_directions,
        "horizon_s": args.horizon_s,
        "tau_s": args.tau_s,
        "strategies": strategies,
        "lambdas": lambdas,
        "kmax_list": kmax_list,
        "seeds": seeds,
        "effective_workers": max_workers,
    }
    summary_path.write_text(json.dumps(summary, indent=2))
    f_raw.close()
    print(f"Wrote {raw_path}")
    print(f"Wrote {agg_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
