"""Sweep pair-distance tolerances to minimize missing representative pairs."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import load_edge_distances_csv
from scripts.qn_topology_feasibility import all_pairs_sp_km, compute_target_feasibility, filter_candidates_by_feasibility


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sweep pair-distance tolerance for representative pairs.")
    p.add_argument("--root-out-dir", type=Path, required=True)
    p.add_argument("--auto-select-topologies", type=int, default=5)
    p.add_argument("--edge-csv-list", type=str, default="")
    p.add_argument("--topology-id-list", type=str, default="")
    p.add_argument("--targets-km", type=str, default="404,511,1002")
    p.add_argument("--pairs-per-target", type=int, default=2)
    p.add_argument("--pair-distance-abs-tol-km", type=float, default=0.0)
    p.add_argument(
        "--tolerances",
        type=str,
        default="0.15,0.2,0.25,0.3,0.35",
        help="Comma list of relative tolerances to sweep.",
    )
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
    p.add_argument("--min-nodes", type=int, default=None)
    p.add_argument("--max-nodes", type=int, default=None)
    p.add_argument("--topologybench-xlsx-dir", type=Path, default=None)
    p.add_argument("--topologybench-zip", type=Path, default=None)
    p.add_argument("--manifest", type=Path, default=None)
    p.add_argument("--no-download", action="store_true")
    p.add_argument("--no-copy", action="store_true")
    return p.parse_args()


def parse_list(raw: str) -> List[str]:
    return [x for x in raw.split(",") if x]


def parse_float_list(raw: str) -> List[float]:
    return [float(x) for x in raw.split(",") if x]


def run_cmd(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def summarize_missing(pairs_csv: Path, pairs_per_target: int, target_count: int) -> Dict[str, object]:
    rows = load_csv(pairs_csv)
    missing_by_label: Dict[str, int] = {}
    total_missing = 0
    for r in rows:
        if r.get("found", "").lower() in ("false", "0"):
            label = r.get("label", "")
            base = label.split("_")[0] if label else ""
            missing_by_label[base] = missing_by_label.get(base, 0) + 1
            total_missing += 1
    total_expected = pairs_per_target * target_count
    found_count = max(total_expected - total_missing, 0)
    completeness = found_count / total_expected if total_expected else 0.0
    return {
        "total_expected": total_expected,
        "found_count": found_count,
        "total_missing": total_missing,
        "completeness": completeness,
        "missing_by_label": missing_by_label,
    }


def select_topologies(args: argparse.Namespace, out_dir: Path) -> Tuple[List[str], List[Path]]:
    edge_csvs = [Path(p) for p in parse_list(args.edge_csv_list)] if args.edge_csv_list else []
    topo_ids = parse_list(args.topology_id_list) if args.topology_id_list else []
    if edge_csvs and topo_ids and len(edge_csvs) != len(topo_ids):
        raise SystemExit("edge-csv-list length must match topology-id-list")
    if edge_csvs and not topo_ids:
        topo_ids = [p.stem for p in edge_csvs]
    if edge_csvs:
        return topo_ids, edge_csvs
    if not topo_ids and not edge_csvs:
        list_csv = out_dir / "topologybench_list.csv"
        list_cmd = [
            "python",
            "scripts/qn_list_topologybench.py",
            "--out-csv",
            str(list_csv),
        ]
        if args.topologybench_xlsx_dir:
            list_cmd += ["--xlsx-dir", str(args.topologybench_xlsx_dir)]
        if args.topologybench_zip:
            list_cmd += ["--zip", str(args.topologybench_zip)]
            if args.no_copy:
                list_cmd += ["--no-copy"]
        if args.manifest:
            list_cmd += ["--manifest", str(args.manifest)]
        if args.no_download:
            list_cmd += ["--no-download"]
        run_cmd(list_cmd)

        list_rows = load_csv(list_csv)
        if args.min_nodes is not None:
            list_rows = [r for r in list_rows if int(r["n_nodes"]) >= args.min_nodes]
        if args.max_nodes is not None:
            list_rows = [r for r in list_rows if int(r["n_nodes"]) <= args.max_nodes]
        topo_ids = [r["topology_id"] for r in list_rows]

    dist_dir = Path("data/topologybench_distances")
    for topo_id in topo_ids:
        out_csv = dist_dir / f"{topo_id}.csv"
        if out_csv.exists():
            edge_csvs.append(out_csv)
            continue
        cmd = [
            "python",
            "scripts/qn_import_distances_from_topologybench_generic.py",
            "--topology-id",
            topo_id,
            "--out-dir",
            str(dist_dir),
        ]
        if args.manifest:
            cmd += ["--manifest", str(args.manifest)]
        if args.no_download:
            cmd += ["--no-download"]
        if args.topologybench_xlsx_dir:
            xlsx_path = args.topologybench_xlsx_dir / f"TOP_75_{topo_id}.xlsx"
            cmd += ["--xlsx", str(xlsx_path)]
        elif args.topologybench_zip:
            cmd += ["--zip", str(args.topologybench_zip)]
            if args.no_copy:
                cmd += ["--no-copy"]
        run_cmd(cmd)
        if not out_csv.exists():
            raise FileNotFoundError(out_csv)
        edge_csvs.append(out_csv)

    return topo_ids, edge_csvs


def main() -> None:
    args = parse_args()
    root_out = args.root_out_dir
    root_out.mkdir(parents=True, exist_ok=True)
    topo_ids, edge_csvs = select_topologies(args, root_out)
    targets = parse_float_list(args.targets_km)
    tolerances = parse_float_list(args.tolerances)

    candidate_meta = {}
    for topo_id, edge_csv in zip(topo_ids, edge_csvs):
        dist_map = load_edge_distances_csv(edge_csv)
        pairs = all_pairs_sp_km(dist_map)
        nodes = set()
        for u, v in dist_map.keys():
            nodes.add(u)
            nodes.add(v)
        n_nodes = len(nodes)
        n_edges = len(dist_map)
        avg_degree = (2 * n_edges / n_nodes) if n_nodes else 0.0
        diameter_km = max((p[0] for p in pairs), default=0.0)
        candidate_meta[topo_id] = {
            "topology_id": topo_id,
            "edge_csv": edge_csv,
            "dist_map": dist_map,
            "pairs": pairs,
            "n_nodes": n_nodes,
            "n_edges": n_edges,
            "avg_degree": avg_degree,
            "diameter_km": diameter_km,
        }

    summary_rows = []
    per_tol_out: Dict[float, Dict[str, object]] = {}
    selected_topologies_by_tol: Dict[float, List[str]] = {}

    for tol in tolerances:
        tol_dir = root_out / f"tol_{str(tol).replace('.', 'p')}"
        tol_dir.mkdir(parents=True, exist_ok=True)
        candidate_rows = []
        for topo_id in topo_ids:
            meta = candidate_meta[topo_id]
            feas = compute_target_feasibility(
                meta["dist_map"],
                targets,
                args.pairs_per_target,
                args.pair_distance_abs_tol_km,
                tol,
                pairs=meta["pairs"],
            )
            candidate_rows.append(
                {
                    "topology_id": topo_id,
                    "n_nodes": meta["n_nodes"],
                    "n_edges": meta["n_edges"],
                    "avg_degree": meta["avg_degree"],
                    "diameter_km": meta["diameter_km"],
                    "missing_total": feas["total_missing"],
                    "missing_long": feas["missing_long"],
                    "completeness": feas["completeness"],
                    "counts_by_label": feas["counts_by_label"],
                }
            )

        eligible = filter_candidates_by_feasibility(
            candidate_rows,
            args.require_long_feasible,
            args.require_target_feasible,
        )
        selection_ok = len(eligible) >= args.auto_select_topologies
        pool = eligible if selection_ok else candidate_rows
        pool = sorted(
            pool,
            key=lambda r: (
                int(r["missing_long"]),
                int(r["missing_total"]),
                -float(r["completeness"]),
                float(r["diameter_km"]),
                str(r["topology_id"]),
            ),
        )
        if selection_ok and not args.require_target_feasible:
            missing_vals = sorted({int(r["missing_total"]) for r in pool})
            staged = []
            for mv in missing_vals:
                for row in pool:
                    if int(row["missing_total"]) == mv:
                        staged.append(row)
                if len(staged) >= args.auto_select_topologies:
                    break
            pool = staged

        selection_pool_csv = tol_dir / "selection_pool.csv"
        with selection_pool_csv.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["topology_id", "n_nodes", "n_edges", "avg_degree", "diameter_km"],
            )
            writer.writeheader()
            for row in pool:
                writer.writerow(
                    {
                        "topology_id": row["topology_id"],
                        "n_nodes": row["n_nodes"],
                        "n_edges": row["n_edges"],
                        "avg_degree": row["avg_degree"],
                        "diameter_km": f"{row['diameter_km']:.2f}",
                    }
                )
        selected_csv = tol_dir / "selected_topologies.csv"
        run_cmd(
            [
                "python",
                "scripts/qn_select_diverse_topologies.py",
                "--list-csv",
                str(selection_pool_csv),
                "--k",
                str(args.auto_select_topologies),
                "--out-csv",
                str(selected_csv),
            ]
        )
        selected_rows = load_csv(selected_csv)
        selected_ids = [r["topology_id"] for r in selected_rows]
        selected_topologies_by_tol[tol] = selected_ids

        total_missing = 0
        total_expected = 0
        missing_long = 0
        for topo_id in topo_ids:
            meta = candidate_meta[topo_id]
            topo_dir = tol_dir / topo_id
            topo_dir.mkdir(parents=True, exist_ok=True)
            pairs_csv = topo_dir / "pairs_repr3.csv"
            run_cmd(
                [
                    "python",
                    "scripts/qn_select_pairs_by_sp_distance.py",
                    "--edge-distance-csv",
                    str(meta["edge_csv"]),
                    "--topology-id",
                    topo_id,
                    "--targets-km",
                    args.targets_km,
                    "--pairs-per-target",
                    str(args.pairs_per_target),
                    "--pair-distance-abs-tol-km",
                    str(args.pair_distance_abs_tol_km),
                    "--pair-distance-rel-tol",
                    str(tol),
                    "--out-csv",
                    str(pairs_csv),
                ]
            )
            stats = summarize_missing(pairs_csv, args.pairs_per_target, len(targets))
            selected_flag = topo_id in selected_ids
            if selected_flag:
                total_missing += stats["total_missing"]
                total_expected += stats["total_expected"]
                missing_long += stats["missing_by_label"].get("long", 0)
            summary_rows.append(
                {
                    "tolerance": tol,
                    "topology_id": topo_id,
                    "label": "all",
                    "total_expected": stats["total_expected"],
                    "found_count": stats["found_count"],
                    "missing_count": stats["total_missing"],
                    "completeness": stats["completeness"],
                    "missing_long": stats["missing_by_label"].get("long", 0),
                    "selected": selected_flag,
                }
            )
            for label, count in stats["missing_by_label"].items():
                summary_rows.append(
                    {
                        "tolerance": tol,
                        "topology_id": topo_id,
                        "label": label,
                        "total_expected": args.pairs_per_target,
                        "found_count": args.pairs_per_target - count,
                        "missing_count": count,
                        "completeness": (args.pairs_per_target - count) / args.pairs_per_target
                        if args.pairs_per_target
                        else 0.0,
                        "missing_long": count if label == "long" else 0,
                        "selected": selected_flag,
                    }
                )
        overall_completeness = (total_expected - total_missing) / total_expected if total_expected else 0.0
        per_tol_out[tol] = {
            "total_missing": total_missing,
            "total_expected": total_expected,
            "overall_completeness": overall_completeness,
            "missing_long": missing_long,
            "tol_dir": str(tol_dir),
            "selection_ok": selection_ok,
            "selected_topologies": selected_ids,
        }
        summary_rows.append(
            {
                "tolerance": tol,
                "topology_id": "SELECTED_SET",
                "label": "all",
                "total_expected": total_expected,
                "found_count": total_expected - total_missing,
                "missing_count": total_missing,
                "completeness": overall_completeness,
                "missing_long": missing_long,
                "selected": True,
            }
        )

    summary_csv = root_out / "tolerance_missing_summary.csv"
    with summary_csv.open("w", newline="") as f:
        fieldnames = [
            "tolerance",
            "topology_id",
            "label",
            "total_expected",
            "found_count",
            "missing_count",
            "completeness",
            "missing_long",
            "selected",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    chosen = None
    reason = ""
    for tol in tolerances:
        stats = per_tol_out[tol]
        if not stats["selection_ok"]:
            continue
        if stats["missing_long"] == 0 and stats["overall_completeness"] >= 0.95:
            chosen = tol
            reason = "missing_long==0 and completeness>=0.95"
            break
    if chosen is None:
        best = sorted(
            tolerances,
            key=lambda t: (
                per_tol_out[t]["missing_long"],
                -per_tol_out[t]["overall_completeness"],
            ),
        )[0]
        chosen = best
        reason = "no tolerance met completeness criteria; chose best completeness/min missing_long"
        print(
            "WARNING: No tolerance met completeness criteria; "
            f"using tol={chosen} (completeness={per_tol_out[chosen]['overall_completeness']:.3f})."
        )

    chosen_path = root_out / "chosen_tolerance.json"
    chosen_path.write_text(
        json.dumps(
            {
                "chosen_tolerance": chosen,
                "reason": reason,
                "tolerances": tolerances,
                "per_tolerance": per_tol_out,
                "selected_topologies_by_tolerance": selected_topologies_by_tol,
                "chosen_topologies": per_tol_out.get(chosen, {}).get("selected_topologies", []),
                "pair_distance_abs_tol_km": args.pair_distance_abs_tol_km,
                "pair_distance_rel_tol_list": tolerances,
                "pairs_per_target": args.pairs_per_target,
                "targets_km": targets,
                "require_target_feasible": args.require_target_feasible,
                "require_long_feasible": args.require_long_feasible,
            },
            indent=2,
        )
    )

    print(f"Wrote {summary_csv}")
    print(f"Wrote {chosen_path}")


if __name__ == "__main__":
    main()
