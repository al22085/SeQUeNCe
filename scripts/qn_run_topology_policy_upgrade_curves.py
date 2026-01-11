"""Run topology+policy upgrade-k curves with binary search (Tier2 default A=0.99)."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import Dict, List

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import load_edge_distances_csv
from scripts.qn_topology_feasibility import (
    all_pairs_sp_km,
    compute_target_feasibility,
    filter_candidates_by_feasibility,
    label_for_target,
)
from sequence.qn.parallel import (
    ParallelVerificationError,
    verify_parallelism,
    get_mp_context,
    validate_workers,
)


def parse_float_list(raw: str) -> List[float]:
    return [float(x) for x in raw.split(",") if x]


 


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Run topology+policy upgrade-k curves across multiple topologies. "
            "Defaults to SLA Tier2 (A=0.99) and balanced swapping. "
            "If no TopologyBench zip/xlsx is provided, downloads the pinned zip into "
            "./data/topologybench/ and imports distances into data/topologybench_distances/."
        )
    )
    p.add_argument("--edge-csv-list", type=str, default="", help="Comma list of edge CSVs (u,v,linkLengthInKm).")
    p.add_argument("--topology-id-list", type=str, default="", help="Comma list of topology ids (optional).")
    p.add_argument("--topologybench-xlsx-dir", type=Path, default=None, help="Directory with TOP_75_*.xlsx")
    p.add_argument("--topologybench-zip", type=Path, default=None, help="Path to real_topologies.zip")
    p.add_argument("--manifest", type=Path, default=None, help="Manifest JSON path override.")
    p.add_argument("--no-download", action="store_true", help="Offline mode; do not download.")
    p.add_argument("--no-copy", action="store_true", help="Do not copy a provided zip into ./data/topologybench/.")
    p.add_argument("--auto-select-topologies", type=int, default=5, help="Auto-select K topologies from TopologyBench.")
    p.add_argument("--upgrade-policies", type=str, default="global_rank,pair_demand,pair_path_only")
    p.add_argument("--upgrade-k-list", type=str, default="0,3,7,21")
    p.add_argument("--upgrade-k-mode", choices=["full_range", "explicit"], default="full_range")
    p.add_argument("--load-max-cap", type=float, default=50.0, help="Max load_max for auto-escalation when clipped.")
    p.add_argument("--eta", type=float, default=0.9)
    p.add_argument("--target", type=float, default=0.99)
    p.add_argument("--kbits", type=float, default=1.0)
    p.add_argument("--seeds", type=str, default="0,1,2,3")
    p.add_argument("--targets-km", type=str, default="404,511,1002")
    p.add_argument("--pairs-per-target", type=int, default=1)
    p.add_argument("--pair-distance-abs-tol-km", type=float, default=0.0)
    p.add_argument("--pair-distance-rel-tol", type=float, default=0.15)
    p.add_argument(
        "--require-target-feasible",
        action="store_true",
        help="Require all targets to have at least pairs-per-target pairs within tolerance.",
    )
    p.add_argument(
        "--require-long-feasible",
        action="store_true",
        help="Require long target to have at least pairs-per-target pairs within tolerance.",
    )
    p.add_argument("--min-nodes", type=int, default=None, help="Min nodes when auto-selecting diverse topologies.")
    p.add_argument("--max-nodes", type=int, default=None, help="Max nodes when auto-selecting diverse topologies.")
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--loss-db-per-km", type=float, default=0.2)
    p.add_argument("--swap-schedule", type=str, default="balanced", help="Swapping schedule (e.g., balanced).")
    p.add_argument(
        "--network-scope",
        type=str,
        default="shortest_path",
        help="Network scope for robustness runs (e.g., shortest_path or full).",
    )
    p.add_argument("--attempt-rate-opt-hz", type=float, default=5000)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=10000)
    p.add_argument("--coherence-opt-s", type=float, default=0.05)
    p.add_argument("--coherence-sc-s", type=float, default=0.1)
    p.add_argument("--horizon-s", type=float, default=0.3)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--load-min", type=float, default=0.001)
    p.add_argument("--load-max", type=float, default=5.0)
    p.add_argument("--load-tol", type=float, default=0.05)
    p.add_argument("--binary-search", action="store_true", help="Use binary search for frontier (default).")
    p.add_argument("--no-binary-search", dest="binary_search", action="store_false", help="Disable binary search.")
    p.add_argument("--verify-parallel", action="store_true", help="Verify ProcessPool parallelism before running.")
    p.add_argument("--no-verify-parallel", dest="verify_parallel", action="store_false", help="Skip parallelism verification.")
    p.add_argument("--preflight", dest="verify_parallel", action="store_true", help="Alias for --verify-parallel.")
    p.add_argument("--no-preflight", dest="verify_parallel", action="store_false", help="Alias for --no-verify-parallel.")
    p.add_argument("--preflight-strict", action="store_true", help="Require near-full CPU usage in preflight.")
    p.add_argument("--no-preflight-strict", dest="preflight_strict", action="store_false", help="Disable strict CPU threshold.")
    p.add_argument(
        "--verify-parallel-mode",
        choices=["pid_only", "pid_activity", "pid_activity_strict", "speedup"],
        default="pid_activity_strict",
        help="Parallel preflight mode (default: pid_activity_strict).",
    )
    p.add_argument("--preflight-workers", type=int, default=0, help="Override preflight workers (0=use --workers).")
    p.add_argument("--preflight-task-seconds", type=float, default=3.0, help="CPU spin seconds per preflight task.")
    p.add_argument("--preflight-num-tasks", type=int, default=0, help="Override number of preflight tasks (0=auto).")
    p.add_argument("--verify-parallel-overhead", type=float, default=3.0, help="Overhead factor for speedup mode.")
    p.add_argument("--utilization-monitor-seconds", type=float, default=60.0, help="Seconds between utilization samples during run.")
    p.add_argument("--utilization-monitor-samples", type=int, default=5, help="Number of utilization samples during run.")
    p.add_argument(
        "--task-granularity",
        choices=["topo_policy", "topo_policy_pair_seed", "topo_policy_pair_seed_k"],
        default="topo_policy_pair_seed",
        help="Task granularity passed to robustness runner.",
    )
    p.add_argument(
        "--mp-start-method",
        type=str,
        default="",
        help="Multiprocessing start method (e.g., fork, spawn). Empty uses default.",
    )
    p.add_argument("--allow-thread-fallback", action="store_true", help="Allow ThreadPool fallback if ProcessPool fails.")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out-dir", type=Path, default=Path("out/topology_policy_upgrade_curves"))
    p.set_defaults(binary_search=True, verify_parallel=True, preflight_strict=True)
    return p.parse_args()


def parse_list(raw: str) -> List[str]:
    return [x for x in raw.split(",") if x]


def run_cmd(cmd: List[str]):
    subprocess.run(cmd, check=True)


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def summarize_pair_errors(pairs_csv: Path) -> Dict[str, Dict[str, float]]:
    rows = load_csv(pairs_csv)
    by_label: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        if r.get("found", "").lower() in ("false", "0"):
            continue
        label = r["label"].split("_")[0]
        by_label.setdefault(label, []).append(r)
    summary: Dict[str, Dict[str, float]] = {}
    for label, vals in by_label.items():
        abs_errs = [float(v["abs_error_km"]) for v in vals if v["abs_error_km"]]
        rel_errs = [float(v["rel_error"]) for v in vals if v["rel_error"]]
        if not abs_errs or not rel_errs:
            continue
        abs_errs_sorted = sorted(abs_errs)
        rel_errs_sorted = sorted(rel_errs)
        mid = len(abs_errs_sorted) // 2
        summary[label] = {
            "abs_median": abs_errs_sorted[mid],
            "abs_max": max(abs_errs_sorted),
            "rel_median": rel_errs_sorted[mid],
            "rel_max": max(rel_errs_sorted),
        }
    return summary


def summarize_missing_pairs(pairs_csv: Path) -> Dict[str, object]:
    rows = load_csv(pairs_csv)
    missing_by_label: Dict[str, int] = {}
    total_missing = 0
    for r in rows:
        if r.get("found", "").lower() in ("false", "0"):
            label = r["label"].split("_")[0]
            missing_by_label[label] = missing_by_label.get(label, 0) + 1
            total_missing += 1
    return {
        "total_missing": total_missing,
        "missing_by_label": missing_by_label,
    }


def ensure_distance_csv(
    topology_id: str,
    out_dir: Path,
    xlsx_dir: Path | None,
    zip_path: Path | None,
    manifest: Path | None,
    no_download: bool,
    no_copy: bool,
) -> Path:
    out_csv = out_dir / f"{topology_id}.csv"
    if out_csv.exists():
        return out_csv
    cmd = [
        "python",
        "scripts/qn_import_distances_from_topologybench_generic.py",
        "--topology-id",
        topology_id,
        "--out-dir",
        str(out_dir),
    ]
    if manifest:
        cmd += ["--manifest", str(manifest)]
    if no_download:
        cmd += ["--no-download"]
    if xlsx_dir:
        xlsx_path = xlsx_dir / f"TOP_75_{topology_id}.xlsx"
        cmd += ["--xlsx", str(xlsx_path)]
    elif zip_path:
        cmd += ["--zip", str(zip_path)]
        if no_copy:
            cmd += ["--no-copy"]
    run_cmd(cmd)
    if not out_csv.exists():
        raise FileNotFoundError(out_csv)
    return out_csv


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    try:
        effective_workers = validate_workers(args.workers, min_workers=2, max_workers=20)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    parallel_report = None
    if args.verify_parallel:
        preflight_workers = args.preflight_workers or effective_workers
        strict_mode = args.preflight_strict
        verify_mode = args.verify_parallel_mode
        if strict_mode:
            verify_mode = "pid_activity_strict"
        try:
            info = verify_parallelism(
                preflight_workers,
                mode=verify_mode,
                task_seconds=args.preflight_task_seconds,
                num_tasks=(args.preflight_num_tasks or None),
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
            limit_info = info.get("cpu_limit_info", {})
            print(
                "CPU limit summary: "
                f"affinity_cpus={limit_info.get('affinity_cpus')} "
                f"cpuset_cores={limit_info.get('cpuset_cores')} "
                f"quota_cores={limit_info.get('quota_cores')} "
                f"effective_cpu_limit={limit_info.get('effective_cpu_limit')} "
                f"limit_reason={limit_info.get('limit_reason')}"
            )
            print(
                "CPU throttling: "
                f"throttled_detected={info.get('throttled_detected')} "
                f"throttled_usec_delta={info.get('throttled_usec_delta')} "
                f"nr_throttled_delta={info.get('nr_throttled_delta')}"
            )
        except ParallelVerificationError as exc:
            parallel_report = {
                "requested_workers": args.workers,
                "effective_workers": effective_workers,
                "verify_mode": verify_mode,
                "verify_info": exc.report,
                "error": str(exc),
            }
            report_path = args.out_dir / "parallel_report.json"
            report_path.write_text(json.dumps(parallel_report, indent=2))
            raise SystemExit(str(exc)) from exc
        except Exception as exc:
            if args.allow_thread_fallback:
                print(f"Parallel verification failed ({exc}); proceeding with thread fallback allowed")
            else:
                raise SystemExit(f"Parallel verification failed: {exc}") from exc
        parallel_report = {
            "requested_workers": args.workers,
            "effective_workers": effective_workers,
            "verify_mode": verify_mode,
            "verify_info": info,
        }
        report_path = args.out_dir / "parallel_report.json"
        report_path.write_text(json.dumps(parallel_report, indent=2))

    edge_csvs = [Path(p) for p in parse_list(args.edge_csv_list)] if args.edge_csv_list else []
    topo_ids = parse_list(args.topology_id_list) if args.topology_id_list else []
    policies = parse_list(args.upgrade_policies)

    if edge_csvs and topo_ids and len(edge_csvs) != len(topo_ids):
        raise SystemExit("edge-csv-list length must match topology-id-list")
    if args.no_download and not args.topologybench_xlsx_dir and not args.topologybench_zip and not edge_csvs:
        raise SystemExit("No topology source provided with --no-download; supply --edge-csv-list or --topologybench-zip.")

    if not edge_csvs and not topo_ids:
        if args.auto_select_topologies <= 0:
            raise SystemExit("Provide --edge-csv-list/--topology-id-list or --auto-select-topologies")
        list_csv = args.out_dir / "topologybench_list.csv"

        def run_list() -> List[Dict[str, str]]:
            list_cmd = ["python", "scripts/qn_list_topologybench.py", "--out-csv", str(list_csv)]
            if args.topologybench_xlsx_dir:
                list_cmd += ["--xlsx-dir", str(args.topologybench_xlsx_dir)]
            elif args.topologybench_zip:
                list_cmd += ["--zip", str(args.topologybench_zip)]
                if args.no_copy:
                    list_cmd += ["--no-copy"]
            if args.manifest:
                list_cmd += ["--manifest", str(args.manifest)]
            if args.no_download:
                list_cmd += ["--no-download"]
            run_cmd(list_cmd)
            return load_csv(list_csv)

        rows = run_list()
        if len(rows) < args.auto_select_topologies:
            if not args.no_download:
                fetch_cmd = [
                    "python",
                    "scripts/qn_topologybench_fetch.py",
                    "--force-download",
                ]
                if args.manifest:
                    fetch_cmd += ["--manifest", str(args.manifest)]
                run_cmd(fetch_cmd)
                rows = run_list()
            if len(rows) < args.auto_select_topologies:
                raise SystemExit(
                    f"TopologyBench zip appears to contain only {len(rows)} topologies "
                    f"(likely a test fixture). Please fetch the pinned full zip via "
                    f"scripts/qn_topologybench_fetch.py, expected >= {args.auto_select_topologies}."
                )

        targets = parse_float_list(args.targets_km)
        dist_dir = Path("data/topologybench_distances")
        eligibility_rows = []
        candidate_rows = []
        for r in rows:
            topo_id = r["topology_id"]
            edge_csv = ensure_distance_csv(
                topo_id,
                dist_dir,
                args.topologybench_xlsx_dir,
                args.topologybench_zip,
                args.manifest,
                args.no_download,
                args.no_copy,
            )
            dist_map = load_edge_distances_csv(edge_csv)
            pairs = all_pairs_sp_km(dist_map)
            diameter_km = max((p[0] for p in pairs), default=0.0)
            feas = compute_target_feasibility(
                dist_map,
                targets,
                args.pairs_per_target,
                args.pair_distance_abs_tol_km,
                args.pair_distance_rel_tol,
                pairs=pairs,
            )
            counts = feas["counts_by_label"]
            missing_by_label = feas["missing_by_label"]
            missing_total = feas["total_missing"]
            completeness = feas["completeness"]
            missing_long = feas["missing_long"]
            eligibility_rows.append(
                {
                    "topology_id": topo_id,
                    "n_nodes": r["n_nodes"],
                    "n_edges": r["n_edges"],
                    "avg_degree": r["avg_degree"],
                    "diameter_km": f"{diameter_km:.2f}",
                    **{f"count_{t}": counts.get(label_for_target(i, t), 0) for i, t in enumerate(targets)},
                    "missing_total": missing_total,
                    "missing_long": missing_long,
                    "completeness": f"{completeness:.6f}",
                    "eligible": feas["feasible_all_targets"],
                }
            )
            candidate_rows.append(
                {
                    "topology_id": topo_id,
                    "n_nodes": r["n_nodes"],
                    "n_edges": r["n_edges"],
                    "avg_degree": r["avg_degree"],
                    "diameter_km": f"{diameter_km:.2f}",
                    "missing_total": missing_total,
                    "missing_long": missing_long,
                    "completeness": completeness,
                }
            )

        print(f"Topologies found: {len(rows)}")
        eligible_count = sum(1 for r in eligibility_rows if r["eligible"])
        print(f"Eligible under tolerance: {eligible_count}")
        for row in eligibility_rows:
            counts_str = ", ".join([f"{k}={row[k]}" for k in row if k.startswith("count_")])
            print(f"{row['topology_id']} diameter_km={row['diameter_km']} {counts_str} eligible={row['eligible']}")
        eligibility_csv = args.out_dir / "topologybench_list_eligibility.csv"
        with eligibility_csv.open("w", newline="") as f:
            fieldnames = list(eligibility_rows[0].keys()) if eligibility_rows else []
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(eligibility_rows)

        filtered_candidates = filter_candidates_by_feasibility(
            candidate_rows,
            args.require_long_feasible,
            args.require_target_feasible,
        )
        if args.require_long_feasible or args.require_target_feasible:
            if len(filtered_candidates) < args.auto_select_topologies:
                raise SystemExit(
                    "Not enough topologies satisfy feasibility constraints "
                    f"(require_long_feasible={args.require_long_feasible}, "
                    f"require_target_feasible={args.require_target_feasible}). "
                    "Relax tolerance or constraints, or reduce --auto-select-topologies."
                )
            # keep only best-missing candidates if we have more than needed
            if not args.require_target_feasible:
                missing_vals = sorted({int(r['missing_total']) for r in filtered_candidates})
                pool: List[Dict[str, object]] = []
                for mv in missing_vals:
                    for row in filtered_candidates:
                        if int(row["missing_total"]) == mv:
                            pool.append(row)
                    if len(pool) >= args.auto_select_topologies:
                        break
                filtered_candidates = pool

        selection_csv = args.out_dir / "topologybench_list_selection.csv"
        with selection_csv.open("w", newline="") as f:
            fieldnames = ["topology_id", "n_nodes", "n_edges", "avg_degree", "diameter_km"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in filtered_candidates if (args.require_long_feasible or args.require_target_feasible) else candidate_rows:
                writer.writerow({k: row[k] for k in fieldnames})

        if len(candidate_rows) < args.auto_select_topologies:
            raise SystemExit(
                f"Not enough topologies available in list: have {len(candidate_rows)}, "
                f"requested {args.auto_select_topologies}."
            )

        selected_csv = args.out_dir / "topologybench_selected.csv"
        select_cmd = [
            "python",
            "scripts/qn_select_diverse_topologies.py",
            "--list-csv",
            str(selection_csv),
            "--k",
            str(args.auto_select_topologies),
            "--out-csv",
            str(selected_csv),
        ]
        if args.min_nodes is None and args.max_nodes is None:
            print("node_filter=none")
        if args.min_nodes is not None:
            select_cmd += ["--min-nodes", str(args.min_nodes)]
        if args.max_nodes is not None:
            select_cmd += ["--max-nodes", str(args.max_nodes)]
        run_cmd(select_cmd)
        selected = load_csv(selected_csv)
        topo_ids = [r["topology_id"] for r in selected]
        selection_meta = {
            "requested_k": args.auto_select_topologies,
            "selected_k": len(topo_ids),
            "selected_topologies": topo_ids,
            "source_list_csv": str(list_csv),
            "eligibility_list_csv": str(eligibility_csv),
            "selection_list_csv": str(selection_csv),
            "pair_distance_abs_tol_km": args.pair_distance_abs_tol_km,
            "pair_distance_rel_tol": args.pair_distance_rel_tol,
            "require_target_feasible": args.require_target_feasible,
            "require_long_feasible": args.require_long_feasible,
            "node_filter": {
                "min_nodes": args.min_nodes,
                "max_nodes": args.max_nodes,
                "applied": args.min_nodes is not None or args.max_nodes is not None,
            },
        }
        (args.out_dir / "topology_selection.json").write_text(json.dumps(selection_meta, indent=2))

    if topo_ids and not edge_csvs:
        dist_dir = Path("data/topologybench_distances")
        for topo_id in topo_ids:
            edge_csvs.append(
                ensure_distance_csv(
                    topo_id,
                    dist_dir,
                    args.topologybench_xlsx_dir,
                    args.topologybench_zip,
                    args.manifest,
                    args.no_download,
                    args.no_copy,
                )
            )

    if edge_csvs and not topo_ids:
        topo_ids = [p.stem for p in edge_csvs]

    if len(edge_csvs) != len(topo_ids):
        raise SystemExit("edge-csv-list length must match topology-id-list")

    if (args.require_long_feasible or args.require_target_feasible) and topo_ids:
        targets = parse_float_list(args.targets_km)
        feasibility_rows = []
        for topo_id, edge_csv in zip(topo_ids, edge_csvs):
            dist_map = load_edge_distances_csv(edge_csv)
            pairs = all_pairs_sp_km(dist_map)
            diameter_km = max((p[0] for p in pairs), default=0.0)
            feas = compute_target_feasibility(
                dist_map,
                targets,
                args.pairs_per_target,
                args.pair_distance_abs_tol_km,
                args.pair_distance_rel_tol,
                pairs=pairs,
            )
            feasibility_rows.append(
                {
                    "topology_id": topo_id,
                    "diameter_km": f"{diameter_km:.2f}",
                    "missing_total": feas["total_missing"],
                    "missing_long": feas["missing_long"],
                    "completeness": f"{feas['completeness']:.6f}",
                }
            )
        feasibility_csv = args.out_dir / "topologybench_list_eligibility.csv"
        with feasibility_csv.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["topology_id", "diameter_km", "missing_total", "missing_long", "completeness"],
            )
            writer.writeheader()
            writer.writerows(feasibility_rows)
        for row in feasibility_rows:
            missing_total = int(row["missing_total"])
            missing_long = int(row["missing_long"])
            if args.require_long_feasible and missing_long > 0:
                raise SystemExit(
                    f"Topology {row['topology_id']} missing long pairs under tolerance; "
                    "relax tolerance or disable --require-long-feasible."
                )
            if args.require_target_feasible and missing_total > 0:
                raise SystemExit(
                    f"Topology {row['topology_id']} missing target pairs under tolerance; "
                    "relax tolerance or disable --require-target-feasible."
                )

    summary_rows = []
    for topo_id, edge_csv in zip(topo_ids, edge_csvs):
        # compute per-topology Kmax from original edges
        dist_map = load_edge_distances_csv(edge_csv)
        nodes = set()
        for u, v in dist_map.keys():
            nodes.add(u)
            nodes.add(v)
        node_count = len(nodes)
        kmax = len(dist_map)
        if kmax <= 0:
            raise SystemExit(f"No edges found in {edge_csv}")
        if args.upgrade_k_mode == "full_range":
            upgrade_ks = list(range(0, kmax + 1))
        else:
            upgrade_ks = [int(x) for x in parse_list(args.upgrade_k_list)]
        topo_dir = args.out_dir / topo_id
        topo_dir.mkdir(parents=True, exist_ok=True)
        (topo_dir / "upgrade_k_list.json").write_text(
            json.dumps(
                {
                    "topology_id": topo_id,
                    "node_count_original": node_count,
                    "edge_count_original": kmax,
                    "kmax": kmax,
                    "upgrade_k_mode": args.upgrade_k_mode,
                    "upgrade_k_list": upgrade_ks,
                    "upgrade_k_count": len(upgrade_ks),
                    "upgrade_policies": policies,
                },
                indent=2,
            )
        )
        pairs_csv = topo_dir / "pairs_repr3.csv"
        run_cmd(
            [
                "python",
                "scripts/qn_select_pairs_by_sp_distance.py",
                "--edge-distance-csv",
                str(edge_csv),
                "--topology-id",
                topo_id,
                "--targets-km",
                args.targets_km,
                "--pairs-per-target",
                str(args.pairs_per_target),
                "--pair-distance-abs-tol-km",
                str(args.pair_distance_abs_tol_km),
                "--pair-distance-rel-tol",
                str(args.pair_distance_rel_tol),
                "--out-csv",
                str(pairs_csv),
            ]
        )
        # verify errors are within tolerance (median per label group) for found pairs
        summary_errs = summarize_pair_errors(pairs_csv)
        missing_info = summarize_missing_pairs(pairs_csv)
        for label, errs in summary_errs.items():
            if args.pair_distance_abs_tol_km and errs["abs_median"] > args.pair_distance_abs_tol_km:
                raise SystemExit(
                    f"{topo_id} {label} median abs_error {errs['abs_median']:.2f} km exceeds "
                    f"abs tol {args.pair_distance_abs_tol_km}"
                )
            if args.pair_distance_rel_tol and errs["rel_median"] > args.pair_distance_rel_tol:
                raise SystemExit(
                    f"{topo_id} {label} median rel_error {errs['rel_median']:.3f} exceeds "
                    f"rel tol {args.pair_distance_rel_tol}"
                )
        print(f"{topo_id} pair error summary: {summary_errs}")
        if missing_info["total_missing"]:
            print(f"{topo_id} missing pairs: {missing_info}")
        for policy in policies:
            run_out = topo_dir / policy
            run_out.mkdir(parents=True, exist_ok=True)
            pair_frontier = run_out / "robust_frontier_pairs.csv"
            curve_points = run_out / "curve_points.csv"
            curve_metrics = run_out / "curve_metrics.csv"
            if pair_frontier.exists() and curve_points.exists() and curve_metrics.exists():
                metrics_rows = load_csv(curve_metrics)
                load_max_used = args.load_max
            else:
                load_max = args.load_max
                while True:
                    cmd = [
                        "python",
                        "scripts/qn_entanglement_service_robustness_frontier.py",
                        "--pairs-csv",
                        str(pairs_csv),
                        "--etas",
                        str(args.eta),
                        "--strategies",
                        "BK,EQT",
                        "--upgrade-k-list",
                        ",".join(str(k) for k in upgrade_ks),
                        "--targets",
                        str(args.target),
                        "--kbits-list",
                        str(args.kbits),
                        "--seeds",
                        args.seeds,
                        "--load-min",
                        str(args.load_min),
                        "--load-max",
                        str(load_max),
                        "--load-tol",
                        str(args.load_tol),
                        "--horizon-s",
                        str(args.horizon_s),
                        "--tau-s",
                        str(args.tau_s),
                        "--attempt-rate-opt-hz",
                        str(args.attempt_rate_opt_hz),
                        "--attempt-rate-sc-hz",
                        str(args.attempt_rate_sc_hz),
                        "--coherence-opt-s",
                        str(args.coherence_opt_s),
                        "--coherence-sc-s",
                        str(args.coherence_sc_s),
                        "--loss-db-per-km",
                        str(args.loss_db_per_km),
                        "--segment-length-km",
                        str(args.segment_length_km),
                        "--edge-distance-csv",
                        str(edge_csv),
                        "--distance-dataset-id",
                        topo_id,
                        "--network-scope",
                        args.network_scope,
                        "--swap-schedule",
                        args.swap_schedule,
                        "--upgrade-policy",
                        policy,
                        "--topology-id",
                        topo_id,
                        "--workers",
                        str(effective_workers),
                        "--out-dir",
                        str(run_out),
                    ]
                    if args.binary_search:
                        cmd.append("--binary-search")
                    cmd.append("--no-verify-parallel")
                    cmd += ["--task-granularity", args.task_granularity]
                    cmd += ["--utilization-monitor-seconds", str(args.utilization_monitor_seconds)]
                    cmd += ["--utilization-monitor-samples", str(args.utilization_monitor_samples)]
                    if args.mp_start_method:
                        cmd += ["--mp-start-method", args.mp_start_method]
                    if args.allow_thread_fallback:
                        cmd.append("--allow-thread-fallback")
                    run_cmd(cmd)
                    runtime_report = run_out / "parallel_runtime_report.json"
                    if parallel_report is not None and runtime_report.exists():
                        runtime_data = json.loads(runtime_report.read_text())
                        parallel_report.setdefault("runtime_reports", {})[f"{topo_id}/{policy}"] = runtime_data
                        (args.out_dir / "parallel_report.json").write_text(json.dumps(parallel_report, indent=2))

                    curve_csv = run_out / "upgrade_k_curve_numbers.csv"
                    run_cmd(
                        [
                            "python",
                            "scripts/qn_export_upgrade_k_curve.py",
                            "--pair-frontier",
                            str(pair_frontier),
                            "--out-csv",
                            str(curve_csv),
                            "--pairs-csv",
                            str(pairs_csv),
                            "--curve-points-csv",
                            str(curve_points),
                            "--curve-metrics-csv",
                            str(curve_metrics),
                            "--target",
                            str(args.target),
                            "--eta",
                            str(args.eta),
                            "--kbits",
                            str(args.kbits),
                            "--upgrade-ks",
                            ",".join(str(k) for k in upgrade_ks),
                            "--load-max",
                            str(load_max),
                            "--topology-id",
                            topo_id,
                            "--upgrade-policy",
                            policy,
                        ]
                    )
                    metrics_rows = load_csv(curve_metrics)
                    any_clipped = any(r.get("clipped", "").lower() in ("1", "true") for r in metrics_rows)
                    load_max_used = load_max
                    if any_clipped and load_max < args.load_max_cap:
                        load_max = min(args.load_max_cap, load_max * 2)
                        continue
                    break


            for metric in ("median", "worst_case"):
                row = next((r for r in metrics_rows if r["pair"] == metric), None)
                if not row:
                    continue
                summary_rows.append(
                    {
                        "topology_id": topo_id,
                        "policy": policy,
                        "metric": metric,
                        "eta": args.eta,
                        "target_A": args.target,
                        "kbits": args.kbits,
                        "kmax": kmax,
                        "upgrade_k_count": len(upgrade_ks),
                        "ratio_k21": row.get("ratio_k21", ""),
                        "r2": row.get("r2", ""),
                        "curvature": row.get("curvature", ""),
                        "classification": row.get("classification", ""),
                        "clipped": row.get("clipped", ""),
                        "load_max_used": load_max_used,
                        "missing_pairs_total": missing_info["total_missing"],
                        "missing_pairs_by_label": json.dumps(missing_info["missing_by_label"]),
                        "pairs_csv": str(pairs_csv),
                        "curve_points_csv": str(curve_points),
                        "curve_metrics_csv": str(curve_metrics),
                    }
                )

    summary_path = args.out_dir / "summary_upgrade_curves.csv"
    with summary_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "topology_id",
                "policy",
                "metric",
                "eta",
                "target_A",
                "kbits",
                "ratio_k21",
                "kmax",
                "upgrade_k_count",
                "r2",
                "curvature",
                "classification",
                "clipped",
                "load_max_used",
                "missing_pairs_total",
                "missing_pairs_by_label",
                "pairs_csv",
                "curve_points_csv",
                "curve_metrics_csv",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
