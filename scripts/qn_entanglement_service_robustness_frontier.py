"""Robustness frontier across multiple pairs/etas/upgrades for entanglement-service."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED

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
    build_topology_from_dist_map,
    edge_usage_counts_for_pairs,
    orig_edges_in_path,
    edge_usage_counts,
)
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service
from sequence.qn.parallel import (
    ParallelVerificationError,
    verify_parallelism,
    get_mp_context,
    validate_workers,
    sample_pid_cpu,
    collect_worker_pids,
    list_child_pids,
)
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def parse_pairs(raw: str) -> List[Tuple[str, str]]:
    return [tuple(p.split("-")) for p in raw.split(",") if p]


@dataclass
class RobustEvalTask:
    topology_id: str
    pair: Tuple[str, str]
    path_edges: List[Tuple[str, str, float, Tuple[str, str]]]
    eta_val: float
    upgrade_k: int
    strategy: str
    kbits: float
    upgrade_policy: str
    upgraded_edges: List[Tuple[str, str]]
    knobs: StrategyKnobs
    seeds: List[int]
    targets: List[float]
    load_grid: List[float]
    load_min: float
    load_max: float
    load_tol: float
    binary_search: bool
    horizon_s: float
    tau_s: float
    otp_data_rate_bps: float
    otp_session_duration_s: float
    otp_directions: int
    swap_schedule: str
    seed: int | None = None


def _eval_robustness_task(task: RobustEvalTask):
    pair = task.pair
    path_edges = task.path_edges
    eta_val = task.eta_val
    uk = task.upgrade_k
    strat = task.strategy
    kb = task.kbits
    if task.upgrade_policy == "pair_path_only":
        path_orig_edges = orig_edges_in_path(path_edges)
        upgraded_edges = set(path_orig_edges[:uk])
    else:
        upgraded_edges = set(task.upgraded_edges)
    p_bsm, swap_lat = swap_params_for_strategy(strat, task.knobs)

    def evaluate_load(load: float) -> Tuple[float, float]:
        avails = []
        for seed in task.seeds:
            edge_params: Dict[Tuple[str, str], EdgeParams] = {}
            for a, b, dist_m, orig in path_edges:
                dist_km = dist_m / 1000.0
                use_strat = strat if (strat == "BK" or orig in upgraded_edges) else "BK"
                p_eg, attempt_rate, coherence, _, extra_lat = edge_params_for_strategy(
                    use_strat, dist_km, eta_val, task.knobs
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
                horizon_s=task.horizon_s,
                tau_s=task.tau_s,
                num_requests=num_requests,
                lambda_req=None,
                otp_data_rate_bps=task.otp_data_rate_bps,
                otp_session_duration_s=task.otp_session_duration_s,
                otp_directions=task.otp_directions,
                key_bits_per_pair=kb,
                swap_schedule=task.swap_schedule,
            )
            avails.append(res["availability"])
        return float(np.mean(avails)) if avails else 0.0, float(np.std(avails, ddof=0)) if avails else 0.0

    load_rows = []
    frontier_rows = []
    evaluated = set()

    def record(load, mean_av, std_av):
        load_rows.append((load, mean_av, std_av, len(task.seeds), task.seed if task.seed is not None else ""))
        evaluated.add(load)

    if task.binary_search:
        for tgt in task.targets:
            low = task.load_min
            high = task.load_max
            if low not in evaluated:
                m, s = evaluate_load(low)
                record(low, m, s)
            else:
                m = [row for row in load_rows if row[0] == low][0][1]
            if high not in evaluated:
                mh, sh = evaluate_load(high)
                record(high, mh, sh)
            else:
                mh = [row for row in load_rows if row[0] == high][0][1]
            if mh >= tgt:
                frontier = high
                frontier_rows.append(
                    {
                        "topology_id": task.topology_id,
                        "upgrade_policy": task.upgrade_policy,
                        "pair": f"{pair[0]}-{pair[1]}",
                        "eta": eta_val,
                        "strategy": strat,
                        "upgrade_k": uk,
                        "kbits": kb,
                        "target": tgt,
                        "frontier_load": frontier,
                        "seed": task.seed if task.seed is not None else "",
                    }
                )
                continue
            if m < tgt:
                frontier = 0.0
                frontier_rows.append(
                    {
                        "topology_id": task.topology_id,
                        "upgrade_policy": task.upgrade_policy,
                        "pair": f"{pair[0]}-{pair[1]}",
                        "eta": eta_val,
                        "strategy": strat,
                        "upgrade_k": uk,
                        "kbits": kb,
                        "target": tgt,
                        "frontier_load": frontier,
                        "seed": task.seed if task.seed is not None else "",
                    }
                )
                continue
            lo, hi = low, high
            while (hi - lo) > task.load_tol:
                mid = 0.5 * (lo + hi)
                if mid not in evaluated:
                    amid, smid = evaluate_load(mid)
                    record(mid, amid, smid)
                else:
                    amid = [row for row in load_rows if row[0] == mid][0][1]
                if amid >= tgt:
                    lo = mid
                else:
                    hi = mid
            frontier = lo
            frontier_rows.append(
                {
                    "topology_id": task.topology_id,
                    "upgrade_policy": task.upgrade_policy,
                    "pair": f"{pair[0]}-{pair[1]}",
                    "eta": eta_val,
                    "strategy": strat,
                    "upgrade_k": uk,
                    "kbits": kb,
                    "target": tgt,
                    "frontier_load": frontier,
                    "seed": task.seed if task.seed is not None else "",
                }
            )
    else:
        for load in task.load_grid:
            m, s = evaluate_load(load)
            record(load, m, s)
        for tgt in task.targets:
            frontier = 0.0
            for load, mean_av, _, _, _ in load_rows:
                if mean_av >= tgt and load > frontier:
                    frontier = load
            frontier_rows.append(
                {
                    "topology_id": task.topology_id,
                    "upgrade_policy": task.upgrade_policy,
                    "pair": f"{pair[0]}-{pair[1]}",
                    "eta": eta_val,
                    "strategy": strat,
                    "upgrade_k": uk,
                    "kbits": kb,
                    "target": tgt,
                    "frontier_load": frontier,
                    "seed": task.seed if task.seed is not None else "",
                }
            )
    return pair, eta_val, strat, uk, kb, load_rows, frontier_rows


def parse_args():
    p = argparse.ArgumentParser(description="Robustness frontier across pairs/seeds/upgrades.")
    p.add_argument("--pairs-csv", type=Path, default=None, help="CSV from qn_select_nsfnet_pairs.py")
    p.add_argument("--pairs", type=str, default="", help="Comma list like 1-2,3-7")
    p.add_argument("--etas", type=str, default="0.5,0.9")
    p.add_argument("--upgrade-k-list", type=str, default="0,3,7,21")
    p.add_argument(
        "--upgrade-policy",
        choices=["global_rank", "pair_demand", "pair_path_only"],
        default="global_rank",
        help="How to choose upgraded edges.",
    )
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
    p.add_argument("--verify-parallel", action="store_true", help="Verify ProcessPool parallelism before running.")
    p.add_argument("--no-verify-parallel", dest="verify_parallel", action="store_false", help="Skip parallelism verification.")
    p.add_argument(
        "--verify-parallel-mode",
        choices=["pid_only", "pid_activity", "pid_activity_strict", "speedup"],
        default="pid_only",
        help="Parallel preflight mode (default: pid_only).",
    )
    p.add_argument("--verify-parallel-task-seconds", type=float, default=1.0, help="CPU spin seconds per preflight task.")
    p.add_argument("--verify-parallel-num-tasks", type=int, default=0, help="Override number of preflight tasks (0=auto).")
    p.add_argument("--verify-parallel-overhead", type=float, default=3.0, help="Overhead factor for speedup mode.")
    p.add_argument(
        "--mp-start-method",
        type=str,
        default="",
        help="Multiprocessing start method (e.g., fork, spawn). Empty uses default.",
    )
    p.add_argument("--allow-thread-fallback", action="store_true", help="Allow ThreadPool fallback if ProcessPool fails.")
    p.add_argument("--swap-schedule", choices=["sequential", "balanced"], default="sequential")
    p.add_argument(
        "--task-granularity",
        choices=["topo_policy", "topo_policy_pair_seed", "topo_policy_pair_seed_k"],
        default="topo_policy_pair_seed",
        help="Task granularity for ProcessPool tasks.",
    )
    p.add_argument("--utilization-monitor-seconds", type=float, default=60.0, help="Seconds between utilization samples.")
    p.add_argument("--utilization-monitor-samples", type=int, default=5, help="Number of utilization samples.")
    p.add_argument("--topology-id", type=str, default="nsfnet")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_entanglement_service_robustness"))
    p.set_defaults(verify_parallel=True)
    return p.parse_args()


def main():
    args = parse_args()
    try:
        effective_workers = validate_workers(args.workers, min_workers=2, max_workers=20)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if args.verify_parallel:
        try:
            info = verify_parallelism(
                effective_workers,
                mode=args.verify_parallel_mode,
                task_seconds=args.verify_parallel_task_seconds,
                num_tasks=(args.verify_parallel_num_tasks or None),
                overhead_factor=args.verify_parallel_overhead,
                mp_context=get_mp_context(args.mp_start_method or None),
            )
            print(
                "Parallel verify: "
                f"mode={info['verify_mode']} effective_workers={info['effective_workers']} "
                f"pids={info['worker_pids']} start_method={info['start_method']}"
            )
            if info.get("verify_mode") in ("pid_activity", "pid_activity_strict"):
                print(
                    f"Parallel activity: active_workers={info.get('active_workers')} "
                    f"aggregate_cpu={info.get('aggregate_cpu'):.1f}%"
                )
        except ParallelVerificationError as exc:
            raise SystemExit(str(exc)) from exc
        except Exception as exc:
            if args.allow_thread_fallback:
                print(f"Parallel verification failed ({exc}); proceeding with thread fallback allowed")
            else:
                raise SystemExit(f"Parallel verification failed: {exc}") from exc
    pairs: List[Tuple[str, str]] = []
    if args.pairs_csv:
        with args.pairs_csv.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("found", "").lower() in ("false", "0"):
                    continue
                src_key = "src" if "src" in row else "src_node"
                dst_key = "dst" if "dst" in row else "dst_node"
                if src_key not in row or dst_key not in row:
                    raise SystemExit("pairs CSV must include src/dst or src_node/dst_node columns")
                pairs.append((row[src_key], row[dst_key]))
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

    topo = nsfnet_topology()
    if args.edge_distance_csv:
        topo = build_topology_from_dist_map(dist_map)

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

    upgrade_edges_cache = {}
    if args.upgrade_policy == "global_rank":
        counts = edge_usage_counts(topo)
        ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        for uk in upgrade_ks:
            upgrade_edges_cache[uk] = set([e for e, _ in ranked[:uk]])
    elif args.upgrade_policy == "pair_demand":
        counts = edge_usage_counts_for_pairs(expanded_edges, pairs)
        ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        for uk in upgrade_ks:
            upgrade_edges_cache[uk] = set([e for e, _ in ranked[:uk]])

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "robust_frontier_raw.csv"
    pair_path = out_dir / "robust_frontier_pairs.csv"
    agg_path = out_dir / "robust_frontier_agg.csv"
    summary_path = out_dir / "summary.json"

    raw_headers = [
        "topology_id",
        "upgrade_policy",
        "pair",
        "eta",
        "strategy",
        "upgrade_k",
        "kbits",
        "load",
        "availability_mean",
        "availability_std",
        "runs",
        "seed",
    ]

    tasks: List[RobustEvalTask] = []
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
                        if args.task_granularity == "topo_policy":
                            seed_groups = [seeds]
                        else:
                            seed_groups = [[s] for s in seeds]
                        for seed_group in seed_groups:
                            tasks.append(
                                RobustEvalTask(
                                    topology_id=args.topology_id,
                                    pair=pair,
                                    path_edges=path_edges,
                                    eta_val=eta_val,
                                    upgrade_k=uk,
                                    strategy=strat,
                                    kbits=kb,
                                    upgrade_policy=args.upgrade_policy,
                                    upgraded_edges=list(upgrade_edges_cache.get(uk, [])),
                                    knobs=knobs,
                                    seeds=seed_group,
                                    targets=targets,
                                    load_grid=load_grid,
                                    load_min=args.load_min,
                                    load_max=args.load_max,
                                    load_tol=args.load_tol,
                                    binary_search=args.binary_search,
                                    horizon_s=args.horizon_s,
                                    tau_s=args.tau_s,
                                    otp_data_rate_bps=args.otp_data_rate_bps,
                                    otp_session_duration_s=args.otp_session_duration_s,
                                    otp_directions=args.otp_directions,
                                    swap_schedule=args.swap_schedule,
                                    seed=seed_group[0] if len(seed_group) == 1 else None,
                                )
                            )

    mp_ctx = get_mp_context(args.mp_start_method or None)
    print(
        f"Using pool_kind=process effective_workers={effective_workers} "
        f"start_method={mp_ctx.get_start_method()} task_count={len(tasks)} chunksize=1"
    )
    results = []
    try:
        with ProcessPoolExecutor(max_workers=effective_workers, mp_context=mp_ctx) as ex:
            worker_pids = collect_worker_pids(ex, effective_workers)
            fut_map = {ex.submit(_eval_robustness_task, t): t for t in tasks}
            if args.utilization_monitor_samples <= 0:
                for fut in as_completed(fut_map):
                    results.append(fut.result())
            else:
                pending = set(fut_map.keys())
                monitor_records = []
                monitor_left = args.utilization_monitor_samples
                monitor_interval = max(0.5, args.utilization_monitor_seconds)
                sample_interval = max(1.0, min(2.0, monitor_interval / 4.0))
                min_cpu = 0.7 * effective_workers * 100.0
                low_count = 0
                low_required = 2
                while pending:
                    done, pending = wait(pending, timeout=monitor_interval, return_when=FIRST_COMPLETED)
                    for fut in done:
                        results.append(fut.result())
                    if monitor_left > 0 and pending:
                        current_pids = list_child_pids(os.getpid()) or worker_pids
                        sample = sample_pid_cpu(current_pids, interval_s=sample_interval)
                        aggregate_cpu = sum(cpu for _, cpu in sample.values())
                        active_workers = sum(1 for state, cpu in sample.values() if cpu >= 50.0 and "R" in state)
                        monitor_records.append(
                            {
                                "active_workers": active_workers,
                                "aggregate_cpu": aggregate_cpu,
                                "worker_cpu": sample,
                                "pending_tasks": len(pending),
                            }
                        )
                        if aggregate_cpu < min_cpu:
                            low_count += 1
                        else:
                            low_count = 0
                        if low_count >= low_required:
                            for fut in pending:
                                fut.cancel()
                            raise SystemExit(
                                f"Utilization dropped below threshold: aggregate_cpu={aggregate_cpu:.1f}% "
                                f"(min {min_cpu:.1f}%), pending={len(pending)}. "
                                f"active_workers={active_workers}."
                            )
                        monitor_left -= 1
    except Exception as exc:
        if args.allow_thread_fallback:
            print(f"ProcessPool failed ({exc}); falling back to ThreadPool")
            with ThreadPoolExecutor(max_workers=effective_workers) as ex:
                fut_map = {ex.submit(_eval_robustness_task, t): t for t in tasks}
                for fut in as_completed(fut_map):
                    results.append(fut.result())
        else:
            raise SystemExit(f"ProcessPool failed: {exc}") from exc
    if "monitor_records" in locals():
        report = {
            "worker_pids": worker_pids,
            "samples": monitor_records,
        }
        (args.out_dir / "parallel_runtime_report.json").write_text(json.dumps(report, indent=2))

    # write raw (load-level) and pair-level frontier
    with raw_path.open("w", newline="") as f_raw:
        writer = csv.writer(f_raw)
        writer.writerow(raw_headers)
        for pair, eta_val, strat, uk, kb, load_rows, frontier_rows in results:
            for load, mean_av, std_av, runs, seed in load_rows:
                writer.writerow(
                    [
                        args.topology_id,
                        args.upgrade_policy,
                        f"{pair[0]}-{pair[1]}",
                        eta_val,
                        strat,
                        uk,
                        kb,
                        load,
                        mean_av,
                        std_av,
                        runs,
                        seed,
                    ]
                )

    pair_rows = []
    for _, _, _, _, _, _, frontier_rows in results:
        pair_rows.extend(frontier_rows)
    with pair_path.open("w", newline="") as f_pair:
        writer = csv.DictWriter(
            f_pair,
            fieldnames=[
                "topology_id",
                "upgrade_policy",
                "pair",
                "eta",
                "strategy",
                "upgrade_k",
                "kbits",
                "target",
                "frontier_load",
                "seed",
            ],
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
                                "topology_id": args.topology_id,
                                "upgrade_policy": args.upgrade_policy,
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
                "topology_id",
                "upgrade_policy",
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

    summary = {
        "topology_id": args.topology_id,
        "upgrade_policy": args.upgrade_policy,
        "distance_dataset_id": args.distance_dataset_id,
        "pairs": [f"{p[0]}-{p[1]}" for p in pairs],
        "eta_list": etas,
        "upgrade_k_list": upgrade_ks,
        "targets": targets,
        "kbits_list": kbits_list,
        "load_grid": load_grid,
        "binary_search": args.binary_search,
        "load_min": args.load_min,
        "load_max": args.load_max,
        "load_tol": args.load_tol,
    }
    summary_path.write_text(json.dumps(summary, indent=2))

    print(f"Wrote raw to {raw_path}")
    print(f"Wrote pair frontiers to {pair_path}")
    print(f"Wrote agg to {agg_path}")


if __name__ == "__main__":
    main()
