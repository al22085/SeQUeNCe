"""Sweep pair-distance tolerances to minimize missing representative pairs."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple


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

        selected_csv = out_dir / "topologybench_selected.csv"
        select_cmd = [
            "python",
            "scripts/qn_select_diverse_topologies.py",
            "--list-csv",
            str(list_csv),
            "--k",
            str(args.auto_select_topologies),
            "--out-csv",
            str(selected_csv),
        ]
        if args.min_nodes is not None:
            select_cmd += ["--min-nodes", str(args.min_nodes)]
        if args.max_nodes is not None:
            select_cmd += ["--max-nodes", str(args.max_nodes)]
        run_cmd(select_cmd)
        selected_rows = load_csv(selected_csv)
        topo_ids = [r["topology_id"] for r in selected_rows]

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

    summary_rows = []
    per_tol_out = {}
    for tol in tolerances:
        tol_dir = root_out / f"tol_{str(tol).replace('.', 'p')}"
        tol_dir.mkdir(parents=True, exist_ok=True)
        total_missing = 0
        total_expected = 0
        missing_long = 0
        for topo_id, edge_csv in zip(topo_ids, edge_csvs):
            topo_dir = tol_dir / topo_id
            topo_dir.mkdir(parents=True, exist_ok=True)
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
                    str(tol),
                    "--out-csv",
                    str(pairs_csv),
                ]
            )
            stats = summarize_missing(pairs_csv, args.pairs_per_target, len(targets))
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
                    }
                )
        overall_completeness = (total_expected - total_missing) / total_expected if total_expected else 0.0
        per_tol_out[tol] = {
            "total_missing": total_missing,
            "total_expected": total_expected,
            "overall_completeness": overall_completeness,
            "missing_long": missing_long,
            "tol_dir": str(tol_dir),
        }
        summary_rows.append(
            {
                "tolerance": tol,
                "topology_id": "ALL_TOPOLOGIES",
                "label": "all",
                "total_expected": total_expected,
                "found_count": total_expected - total_missing,
                "missing_count": total_missing,
                "completeness": overall_completeness,
                "missing_long": missing_long,
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
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summary_rows)

    chosen = None
    reason = ""
    for tol in tolerances:
        stats = per_tol_out[tol]
        if stats["total_missing"] == 0:
            chosen = tol
            reason = "total_missing==0"
            break
        if stats["overall_completeness"] >= 0.95 and stats["missing_long"] == 0:
            chosen = tol
            reason = "completeness>=0.95 and missing_long==0"
            break
    if chosen is None:
        # pick best completeness
        best_tol = max(tolerances, key=lambda t: (per_tol_out[t]["overall_completeness"], -t))
        chosen = best_tol
        reason = "no tolerance met completeness criteria; chose best completeness"
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
                "selected_topologies": topo_ids,
                "pair_distance_abs_tol_km": args.pair_distance_abs_tol_km,
                "pair_distance_rel_tol_list": tolerances,
                "pairs_per_target": args.pairs_per_target,
                "targets_km": targets,
            },
            indent=2,
        )
    )

    print(f"Wrote {summary_csv}")
    print(f"Wrote {chosen_path}")


if __name__ == "__main__":
    main()
