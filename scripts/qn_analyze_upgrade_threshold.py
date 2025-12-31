"""Analyze upgrade-k threshold via shortest-path coverage and frontier joins."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    load_distance_dataset,
    load_edge_distances_csv,
    subdivide_edges,
    shortest_path_edges,
    nsfnet_topology,
    pick_upgrade_edges,
)


def parse_args():
    p = argparse.ArgumentParser(description="Analyze upgrade-k threshold using path coverage metrics.")
    p.add_argument(
        "--pairs-csv",
        type=Path,
        default=Path("out/nsfnet_pairs_repr3_original.csv"),
        help="Representative pairs CSV (label,src,dst,...)",
    )
    p.add_argument(
        "--frontier-pairs",
        type=Path,
        default=Path("out/ent_robust_upgrade_curve_eta09_t09_binary/robust_frontier_pairs.csv"),
        help="robust_frontier_pairs.csv to enrich with coverage",
    )
    p.add_argument("--out-dir", type=Path, default=Path("out/upgrade_threshold_analysis"))
    p.add_argument("--upgrade-k-list", type=str, default="0,3,7,21")
    p.add_argument("--upgrade-policy", type=str, default="shortestpath_count")
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--edge-distance-csv", type=Path, default=None)
    p.add_argument("--distance-dataset-id", type=str, default="topologybench_nsfnet13")
    return p.parse_args()


def parse_list(raw: str, cast=int):
    return [cast(x) for x in raw.split(",") if x]


def compute_path_coverage(
    expanded_edges: List[Tuple[str, str, float, Tuple[str, str]]],
    src: str,
    dst: str,
    upgraded_edges: set[Tuple[str, str]],
) -> Dict:
    path_edges = shortest_path_edges(expanded_edges, src, dst)
    if not path_edges:
        return {
            "distance_km": 0.0,
            "path_edges_total": 0,
            "path_edges_upgraded": 0,
            "path_upgraded_fraction": 0.0,
            "longest_consecutive_upgraded_run": 0,
        }
    total = len(path_edges)
    upgraded_count = 0
    longest_run = 0
    current_run = 0
    dist_km = 0.0
    for a, b, dist_m, orig in path_edges:
        dist_km += dist_m / 1000.0
        is_upgraded = orig in upgraded_edges
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


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    upgrade_ks = parse_list(args.upgrade_k_list, int)

    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
    expanded_edges, _, _ = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)

    topo = nsfnet_topology()
    upgrade_edges_cache = {k: set(pick_upgrade_edges(topo, args.upgrade_policy, k)) for k in upgrade_ks}

    # load pairs
    pairs = []
    with args.pairs_csv.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            pairs.append(row)

    coverage_rows = []
    for row in pairs:
        src, dst = row["src"], row["dst"]
        label = row.get("label", "")
        for k in upgrade_ks:
            cov = compute_path_coverage(expanded_edges, src, dst, upgrade_edges_cache[k])
            coverage_rows.append(
                {
                    "label": label,
                    "pair": f"{src}-{dst}",
                    "src": src,
                    "dst": dst,
                    "distance_km": cov["distance_km"],
                    "upgrade_k": k,
                    "path_edges_total": cov["path_edges_total"],
                    "path_edges_upgraded": cov["path_edges_upgraded"],
                    "path_upgraded_fraction": cov["path_upgraded_fraction"],
                    "longest_consecutive_upgraded_run": cov["longest_consecutive_upgraded_run"],
                }
            )

    coverage_path = args.out_dir / "upgrade_path_coverage.csv"
    with coverage_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "label",
                "pair",
                "src",
                "dst",
                "distance_km",
                "upgrade_k",
                "path_edges_total",
                "path_edges_upgraded",
                "path_upgraded_fraction",
                "longest_consecutive_upgraded_run",
            ],
        )
        writer.writeheader()
        writer.writerows(coverage_rows)
    print(f"Wrote {coverage_path}")

    # join with frontier pairs if present
    if args.frontier_pairs.exists():
        with args.frontier_pairs.open() as f:
            frontier_rows = list(csv.DictReader(f))
        cov_index = {(r["pair"], int(r["upgrade_k"])): r for r in coverage_rows}
        enriched = []
        for r in frontier_rows:
            key = (r["pair"], int(r["upgrade_k"]))
            cov = cov_index.get(key, {})
            enriched.append(
                {
                    **r,
                    "path_edges_total": cov.get("path_edges_total", ""),
                    "path_edges_upgraded": cov.get("path_edges_upgraded", ""),
                    "path_upgraded_fraction": cov.get("path_upgraded_fraction", ""),
                    "longest_consecutive_upgraded_run": cov.get("longest_consecutive_upgraded_run", ""),
                }
            )
        enriched_path = args.out_dir / "robust_frontier_pairs_enriched.csv"
        with enriched_path.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=list(enriched[0].keys()) if enriched else [],
            )
            if enriched:
                writer.writeheader()
                writer.writerows(enriched)
        print(f"Wrote {enriched_path}")


if __name__ == "__main__":
    main()
