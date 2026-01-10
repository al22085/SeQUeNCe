"""Run topology/policy sensitivity for upgrade-k curves (binary search, balanced)."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Run topology/policy sensitivity for upgrade-k curves. "
            "Defaults to SLA Tier2 (A=0.99) and pinned TopologyBench manifest."
        )
    )
    p.add_argument("--edge-csv-list", type=str, default="", help="Comma list of edge CSVs")
    p.add_argument("--topology-id-list", type=str, default="", help="Comma list of topology ids (optional)")
    p.add_argument("--pairs-csv-list", type=str, default="", help="Comma list of pairs CSVs (optional)")
    p.add_argument("--topologybench-xlsx-dir", type=Path, default=None, help="Directory with TOP_75_*.xlsx")
    p.add_argument("--topologybench-zip", type=Path, default=None, help="Path to real_topologies.zip")
    p.add_argument("--auto-select-topologies", type=int, default=0, help="Auto-select K topologies from TopologyBench")
    p.add_argument("--upgrade-policies", type=str, default="global_rank,pair_demand,pair_path_only")
    p.add_argument("--upgrade-k-list", type=str, default="0,3,7,21")
    p.add_argument("--targets", type=str, default="0.99")
    p.add_argument("--etas", type=str, default="0.9")
    p.add_argument("--kbits-list", type=str, default="1.0")
    p.add_argument("--seeds", type=str, default="0,1,2,3")
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
    p.add_argument("--out-dir", type=Path, default=Path("out/topology_policy_sensitivity"))
    return p.parse_args()


def parse_list(raw: str) -> List[str]:
    return [x for x in raw.split(",") if x]


def run_cmd(cmd: List[str]):
    subprocess.run(cmd, check=True)


def load_csv(path: Path):
    with path.open() as f:
        return list(csv.DictReader(f))


def main():
    args = parse_args()
    if args.workers < 2 or args.workers > 4:
        raise SystemExit("workers must be between 2 and 4")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    edge_csvs = [Path(p) for p in parse_list(args.edge_csv_list)] if args.edge_csv_list else []
    topo_ids = parse_list(args.topology_id_list) if args.topology_id_list else []
    pairs_csvs = parse_list(args.pairs_csv_list) if args.pairs_csv_list else []
    policies = parse_list(args.upgrade_policies)

    if not edge_csvs:
        # auto-select topologies from TopologyBench
        if not args.topologybench_xlsx_dir and not args.topologybench_zip:
            raise SystemExit("Provide --edge-csv-list or TopologyBench source (--topologybench-xlsx-dir/--topologybench-zip)")
        list_csv = args.out_dir / "topologybench_list.csv"
        list_cmd = [
            "python",
            "scripts/qn_list_topologybench.py",
            "--out-csv",
            str(list_csv),
        ]
        if args.topologybench_xlsx_dir:
            list_cmd += ["--xlsx-dir", str(args.topologybench_xlsx_dir)]
        else:
            list_cmd += ["--zip", str(args.topologybench_zip)]
        run_cmd(list_cmd)

        if args.auto_select_topologies <= 0:
            raise SystemExit("Provide --auto-select-topologies when using TopologyBench sources")
        selected_csv = args.out_dir / "topologybench_selected.csv"
        run_cmd(
            [
                "python",
                "scripts/qn_select_diverse_topologies.py",
                "--list-csv",
                str(list_csv),
                "--k",
                str(args.auto_select_topologies),
                "--out-csv",
                str(selected_csv),
            ]
        )
        # import distances for each selected topology
        with selected_csv.open() as f:
            selected = list(csv.DictReader(f))
        for row in selected:
            topo_id = row["topology_id"]
            out_csv = Path("data/topologybench_distances") / f"{topo_id}.csv"
            if not out_csv.exists():
                import_cmd = [
                    "python",
                    "scripts/qn_import_distances_from_topologybench_generic.py",
                    "--topology-id",
                    topo_id,
                    "--out-dir",
                    "data/topologybench_distances",
                ]
                if args.topologybench_xlsx_dir:
                    import_cmd += ["--xlsx", str(args.topologybench_xlsx_dir / f"TOP_75_{topo_id}.xlsx")]
                else:
                    import_cmd += ["--zip", str(args.topologybench_zip)]
                run_cmd(import_cmd)
            edge_csvs.append(out_csv)
            topo_ids.append(topo_id)

    if topo_ids and len(topo_ids) != len(edge_csvs):
        raise SystemExit("topology-id-list length must match edge-csv-list")
    if pairs_csvs and len(pairs_csvs) != len(edge_csvs):
        raise SystemExit("pairs-csv-list length must match edge-csv-list")

    combined_rows = []
    for idx, edge_csv in enumerate(edge_csvs):
        topo_id = topo_ids[idx] if topo_ids else edge_csv.stem
        # build pairs CSV if not provided
        if pairs_csvs:
            pairs_csv = Path(pairs_csvs[idx])
        else:
            pairs_csv = args.out_dir / f"{topo_id}_pairs.csv"
            run_cmd(
                [
                    "python",
                    "scripts/qn_select_topology_pairs.py",
                    "--edge-distance-csv",
                    str(edge_csv),
                    "--segment-length-km",
                    str(args.segment_length_km),
                    "--mode",
                    "literature_anchored",
                    "--out-csv",
                    str(pairs_csv),
                ]
            )

        for policy in policies:
            run_out = args.out_dir / f"{topo_id}_{policy}"
            run_out.mkdir(parents=True, exist_ok=True)
            cmd = [
                "python",
                "scripts/qn_entanglement_service_robustness_frontier.py",
                "--pairs-csv",
                str(pairs_csv),
                "--etas",
                args.etas,
                "--strategies",
                "BK,EQT",
                "--upgrade-k-list",
                args.upgrade_k_list,
                "--targets",
                args.targets,
                "--kbits-list",
                args.kbits_list,
                "--seeds",
                args.seeds,
                "--binary-search",
                "--load-min",
                str(args.load_min),
                "--load-max",
                str(args.load_max),
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

            agg_path = run_out / "robust_frontier_agg.csv"
            agg_rows = load_csv(agg_path)
            for r in agg_rows:
                if r["strategy"] == "BK" and int(r["upgrade_k"]) == 0:
                    bk0 = float(r["frontier_median"])
                    break
            else:
                bk0 = 0.0
            for r in agg_rows:
                ratio = float(r["frontier_median"]) / bk0 if bk0 > 0 else 0.0
                combined_rows.append(
                    {
                        "topology_id": topo_id,
                        "upgrade_policy": policy,
                        "strategy": r["strategy"],
                        "upgrade_k": r["upgrade_k"],
                        "eta": r["eta"],
                        "target": r["target"],
                        "kbits": r["kbits"],
                        "frontier_median": r["frontier_median"],
                        "ratio_vs_bk0": ratio,
                    }
                )

            # simple ratio plot
            ratios = [cr for cr in combined_rows if cr["topology_id"] == topo_id and cr["upgrade_policy"] == policy and cr["strategy"] == "EQT"]
            if ratios:
                xs = [int(r["upgrade_k"]) for r in ratios]
                ys = [float(r["ratio_vs_bk0"]) for r in ratios]
                plt.figure(figsize=(6, 4))
                plt.plot(xs, ys, marker="o")
                plt.xlabel("upgrade_k")
                plt.ylabel("EQT/BK0 ratio (median)")
                plt.title(f"{topo_id} {policy} ratio vs upgrade_k")
                plt.grid(True, alpha=0.3)
                plt.tight_layout()
                plt.savefig(run_out / "ratio_vs_upgrade_k.png")
                plt.close()

    combined_path = args.out_dir / "combined_upgrade_policy_curves.csv"
    with combined_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "topology_id",
                "upgrade_policy",
                "strategy",
                "upgrade_k",
                "eta",
                "target",
                "kbits",
                "frontier_median",
                "ratio_vs_bk0",
            ],
        )
        writer.writeheader()
        writer.writerows(combined_rows)

    meta = {
        "edge_csv_list": [str(p) for p in edge_csvs],
        "topology_id_list": topo_ids if topo_ids else [p.stem for p in edge_csvs],
        "upgrade_policies": policies,
        "upgrade_k_list": args.upgrade_k_list,
        "targets": args.targets,
        "etas": args.etas,
        "kbits_list": args.kbits_list,
    }
    (args.out_dir / "summary.json").write_text(json.dumps(meta, indent=2))
    print(f"Wrote {combined_path}")


if __name__ == "__main__":
    main()
