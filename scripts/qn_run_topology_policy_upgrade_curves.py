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
    p.add_argument("--min-nodes", type=int, default=10, help="Min nodes when auto-selecting diverse topologies.")
    p.add_argument("--max-nodes", type=int, default=30, help="Max nodes when auto-selecting diverse topologies.")
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--loss-db-per-km", type=float, default=0.2)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=5000)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=10000)
    p.add_argument("--coherence-opt-s", type=float, default=0.05)
    p.add_argument("--coherence-sc-s", type=float, default=0.1)
    p.add_argument("--horizon-s", type=float, default=0.3)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--load-min", type=float, default=0.001)
    p.add_argument("--load-max", type=float, default=5.0)
    p.add_argument("--load-tol", type=float, default=0.05)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out-dir", type=Path, default=Path("out/topology_policy_upgrade_curves"))
    return p.parse_args()


def parse_list(raw: str) -> List[str]:
    return [x for x in raw.split(",") if x]


def run_cmd(cmd: List[str]):
    subprocess.run(cmd, check=True)


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


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
    if args.workers < 2 or args.workers > 4:
        raise SystemExit("workers must be between 2 and 4")
    args.out_dir.mkdir(parents=True, exist_ok=True)

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

        selected_csv = args.out_dir / "topologybench_selected.csv"
        run_cmd(
            [
                "python",
                "scripts/qn_select_diverse_topologies.py",
                "--list-csv",
                str(list_csv),
                "--k",
                str(args.auto_select_topologies),
                "--min-nodes",
                str(args.min_nodes),
                "--max-nodes",
                str(args.max_nodes),
                "--out-csv",
                str(selected_csv),
            ]
        )
        selected = load_csv(selected_csv)
        topo_ids = [r["topology_id"] for r in selected]
        if len(topo_ids) < args.auto_select_topologies:
            raise SystemExit(
                f"TopologyBench zip appears to contain only {len(topo_ids)} topologies "
                f"(likely a test fixture). Please fetch the pinned full zip via "
                f"scripts/qn_topologybench_fetch.py, expected >= {args.auto_select_topologies}."
            )
        selection_meta = {
            "requested_k": args.auto_select_topologies,
            "selected_k": len(topo_ids),
            "selected_topologies": topo_ids,
            "source_list_csv": str(list_csv),
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

    summary_rows = []
    for topo_id, edge_csv in zip(topo_ids, edge_csvs):
        # compute per-topology Kmax from original edges
        dist_map = load_edge_distances_csv(edge_csv)
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
                "--out-csv",
                str(pairs_csv),
            ]
        )
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
                        "--binary-search",
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
                        "shortest_path",
                        "--swap-schedule",
                        "balanced",
                        "--upgrade-policy",
                        policy,
                        "--topology-id",
                        topo_id,
                        "--workers",
                        str(args.workers),
                        "--out-dir",
                        str(run_out),
                    ]
                    run_cmd(cmd)

                    curve_csv = run_out / "upgrade_k_curve_numbers.csv"
                    run_cmd(
                        [
                            "python",
                            "scripts/qn_export_upgrade_k_curve.py",
                            "--pair-frontier",
                            str(pair_frontier),
                            "--out-csv",
                            str(curve_csv),
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
