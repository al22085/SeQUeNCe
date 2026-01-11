"""Analyze path upgrade coverage vs frontier ratio across multiple topologies."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.parallel import normalize_workers
from scripts.qn_topologies import (
    build_topology_from_dist_map,
    edge_usage_counts,
    edge_usage_counts_for_pairs,
    load_edge_distances_csv,
    orig_edges_in_path,
    pick_upgrade_edges,
    shortest_path_edges,
    subdivide_edges,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze path coverage and join with curve points.")
    p.add_argument("--root-dir", type=Path, required=True, help="Run root directory.")
    p.add_argument(
        "--distances-dir",
        type=Path,
        default=Path("data/topologybench_distances"),
        help="Directory containing <topology_id>.csv distance files.",
    )
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--ratio-threshold", type=float, default=1.05)
    p.add_argument("--upgrade-policies", type=str, default="global_rank,pair_demand,pair_path_only")
    p.add_argument("--out-dir", type=Path, default=None, help="Output directory (default: root-dir).")
    p.add_argument("--workers", type=int, default=2, help="Worker count for CPU policy validation.")
    return p.parse_args()


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: Iterable[Dict[str, object]], fieldnames: List[str]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def label_base(raw: str) -> str:
    return raw.split("_")[0] if raw else ""


def compute_path_coverage(
    path_edges: List[Tuple[str, str, float, Tuple[str, str]]],
    upgraded_edges: set[Tuple[str, str]],
) -> Dict[str, float]:
    total = len(path_edges)
    upgraded_count = 0
    longest_run = 0
    current_run = 0
    dist_km = 0.0
    for _, _, dist_m, orig in path_edges:
        dist_km += dist_m / 1000.0
        is_upgraded = tuple(sorted(orig)) in upgraded_edges
        if is_upgraded:
            upgraded_count += 1
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0
    frac = upgraded_count / total if total else 0.0
    return {
        "distance_km": dist_km,
        "path_edges_total": total,
        "path_edges_upgraded": upgraded_count,
        "path_upgraded_fraction": frac,
        "longest_consecutive_upgraded_run": longest_run,
    }


def median(values: List[float]) -> float:
    return statistics.median(values) if values else float("nan")


def find_topology_ids(root_dir: Path) -> List[str]:
    selection = root_dir / "topology_selection.json"
    if selection.exists():
        import json

        data = json.loads(selection.read_text(encoding="utf-8"))
        return data.get("selected_topologies", [])
    # fallback to directory scan
    return sorted(p.name for p in root_dir.iterdir() if p.is_dir() and (p / "pairs_repr3.csv").exists())


def main() -> None:
    args = parse_args()
    normalize_workers(args.workers, min_workers=2, max_workers=20)
    out_dir = args.out_dir or args.root_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    policies = [p for p in args.upgrade_policies.split(",") if p]
    topo_ids = find_topology_ids(args.root_dir)
    if not topo_ids:
        raise SystemExit(f"No topology directories found under {args.root_dir}")

    all_join_rows: List[Dict[str, object]] = []
    threshold_rows: List[Dict[str, object]] = []

    for topo_id in topo_ids:
        pairs_csv = args.root_dir / topo_id / "pairs_repr3.csv"
        if not pairs_csv.exists():
            print(f"Skipping {topo_id}: missing pairs_repr3.csv")
            continue
        pairs_rows = load_csv(pairs_csv)
        pairs = [(r["src_node"], r["dst_node"]) for r in pairs_rows]
        pair_label = {f"{r['src_node']}-{r['dst_node']}": label_base(r["label"]) for r in pairs_rows}

        edge_csv = args.distances_dir / f"{topo_id}.csv"
        if not edge_csv.exists():
            raise FileNotFoundError(edge_csv)
        dist_map = load_edge_distances_csv(edge_csv)
        expanded_edges, _, _ = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
        topo = build_topology_from_dist_map(dist_map)

        # Precompute shortest paths once per pair.
        path_edges_by_pair = {f"{s}-{d}": shortest_path_edges(expanded_edges, s, d) for s, d in pairs}
        path_orig_edges_by_pair = {p: orig_edges_in_path(path) for p, path in path_edges_by_pair.items()}

        for policy in policies:
            curve_points_path = args.root_dir / topo_id / policy / "curve_points.csv"
            if not curve_points_path.exists():
                continue
            curve_points = load_csv(curve_points_path)
            upgrade_ks = sorted({int(r["upgrade_k"]) for r in curve_points})

            upgrade_edges_cache: Dict[int, set[Tuple[str, str]]] = {}
            if policy == "global_rank":
                ranked = sorted(edge_usage_counts(topo).items(), key=lambda x: (-x[1], x[0]))
                ranked_edges = [e for e, _ in ranked]
                for k in upgrade_ks:
                    upgrade_edges_cache[k] = set(ranked_edges[:k])
            elif policy == "pair_demand":
                counts = edge_usage_counts_for_pairs(expanded_edges, pairs)
                ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
                ranked_edges = [e for e, _ in ranked]
                for k in upgrade_ks:
                    upgrade_edges_cache[k] = set(ranked_edges[:k])

            coverage_rows: Dict[Tuple[str, int], Dict[str, object]] = {}
            for pair_id, path_edges in path_edges_by_pair.items():
                label = pair_label.get(pair_id, "")
                for k in upgrade_ks:
                    if policy == "pair_path_only":
                        upgraded = set(path_orig_edges_by_pair[pair_id][:k])
                    else:
                        upgraded = upgrade_edges_cache.get(k, set())
                    cov = compute_path_coverage(path_edges, upgraded)
                    coverage_rows[(pair_id, k)] = {
                        "topology_id": topo_id,
                        "upgrade_policy": policy,
                        "pair": pair_id,
                        "label": label,
                        "upgrade_k": k,
                        **cov,
                    }

            # Join with curve points.
            for r in curve_points:
                pair_id = r["pair"]
                k = int(r["upgrade_k"])
                cov = coverage_rows.get((pair_id, k), {})
                all_join_rows.append(
                    {
                        **r,
                        "path_edges_total": cov.get("path_edges_total", ""),
                        "path_edges_upgraded": cov.get("path_edges_upgraded", ""),
                        "path_upgraded_fraction": cov.get("path_upgraded_fraction", ""),
                        "longest_consecutive_upgraded_run": cov.get("longest_consecutive_upgraded_run", ""),
                    }
                )

            # Thresholds per pair/policy.
            ratio_threshold = args.ratio_threshold
            for pair_id in path_edges_by_pair.keys():
                # coverage threshold
                cov_rows = [coverage_rows[(pair_id, k)] for k in upgrade_ks if (pair_id, k) in coverage_rows]
                cov_rows_sorted = sorted(cov_rows, key=lambda r: int(r["upgrade_k"]))
                coverage_threshold_k = None
                for c in cov_rows_sorted:
                    if float(c["path_upgraded_fraction"]) > 0:
                        coverage_threshold_k = int(c["upgrade_k"])
                        break
                # k* from curve points
                cp_rows = [r for r in curve_points if r["pair"] == pair_id]
                cp_rows_sorted = sorted(cp_rows, key=lambda r: int(r["upgrade_k"]))
                k_star = None
                for r in cp_rows_sorted:
                    if float(r["ratio_vs_bk0"]) >= ratio_threshold:
                        k_star = int(r["upgrade_k"])
                        break
                kmax = max(int(r["upgrade_k"]) for r in cp_rows_sorted) if cp_rows_sorted else 0
                threshold_rows.append(
                    {
                        "topology_id": topo_id,
                        "upgrade_policy": policy,
                        "pair": pair_id,
                        "label": pair_label.get(pair_id, ""),
                        "coverage_threshold_k": coverage_threshold_k if coverage_threshold_k is not None else "",
                        "k_star": k_star if k_star is not None else "",
                        "k_star_fraction": (k_star / kmax) if k_star is not None and kmax else "",
                        "path_edges_total": len(path_edges_by_pair[pair_id]),
                        "path_distance_km": sum(d / 1000.0 for _, _, d, _ in path_edges_by_pair[pair_id]),
                        "k_star_minus_coverage": (
                            (k_star - coverage_threshold_k)
                            if k_star is not None and coverage_threshold_k is not None
                            else ""
                        ),
                    }
                )

    join_path = out_dir / "path_coverage_join.csv"
    if all_join_rows:
        write_csv(
            join_path,
            all_join_rows,
            list(all_join_rows[0].keys()),
        )
    print(f"Wrote {join_path}")

    thresholds_path = out_dir / "path_coverage_thresholds.csv"
    if threshold_rows:
        write_csv(
            thresholds_path,
            threshold_rows,
            [
                "topology_id",
                "upgrade_policy",
                "pair",
                "label",
                "coverage_threshold_k",
                "k_star",
                "k_star_fraction",
                "path_edges_total",
                "path_distance_km",
                "k_star_minus_coverage",
            ],
        )
    print(f"Wrote {thresholds_path}")

    # Pooled thresholds summary.
    summary_rows: List[Dict[str, object]] = []
    by_policy: Dict[str, List[Dict[str, object]]] = {}
    by_label: Dict[str, List[Dict[str, object]]] = {}
    for r in threshold_rows:
        by_policy.setdefault(r["upgrade_policy"], []).append(r)
        by_label.setdefault(label_base(r["label"]), []).append(r)
    for policy, rows in sorted(by_policy.items()):
        cov_vals = [float(r["coverage_threshold_k"]) for r in rows if r["coverage_threshold_k"] != ""]
        kstar_vals = [float(r["k_star"]) for r in rows if r["k_star"] != ""]
        summary_rows.append(
            {
                "scope": "policy",
                "upgrade_policy": policy,
                "label": "",
                "n_pairs": len(rows),
                "coverage_threshold_k_median": median(cov_vals),
                "k_star_median": median(kstar_vals),
            }
        )
    for lbl, rows in sorted(by_label.items()):
        cov_vals = [float(r["coverage_threshold_k"]) for r in rows if r["coverage_threshold_k"] != ""]
        kstar_vals = [float(r["k_star"]) for r in rows if r["k_star"] != ""]
        summary_rows.append(
            {
                "scope": "label",
                "upgrade_policy": "",
                "label": lbl,
                "n_pairs": len(rows),
                "coverage_threshold_k_median": median(cov_vals),
                "k_star_median": median(kstar_vals),
            }
        )
    summary_path = out_dir / "path_coverage_thresholds_summary.csv"
    if summary_rows:
        write_csv(
            summary_path,
            summary_rows,
            [
                "scope",
                "upgrade_policy",
                "label",
                "n_pairs",
                "coverage_threshold_k_median",
                "k_star_median",
            ],
        )
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
