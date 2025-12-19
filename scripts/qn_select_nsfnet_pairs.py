"""Select deterministic NSFNET endpoint pairs on expanded graph (TopologyBench, seg=50km)."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    load_distance_dataset,
    load_edge_distances_csv,
    subdivide_edges,
    expanded_nodes,
    shortest_path_edges,
    NSFNET_NODES,
)


def parse_args():
    p = argparse.ArgumentParser(description="Select deterministic NSFNET pairs by longest shortest-path distance.")
    p.add_argument("--k", type=int, default=5, help="Number of pairs to output (default 5).")
    p.add_argument(
        "--distance-dataset-id",
        type=str,
        default="topologybench_nsfnet13",
        help="Distance dataset id (sndlib_great_circle_heuristic | topologybench_nsfnet13)",
    )
    p.add_argument("--edge-distance-csv", type=Path, default=None, help="Optional distance CSV override.")
    p.add_argument("--segment-length-km", type=float, default=50.0, help="Max segment length when subdividing edges.")
    p.add_argument("--out-csv", type=Path, default=Path("out/nsfnet_pairs.csv"))
    return p.parse_args()


def main():
    args = parse_args()
    dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)
    expanded_edges, mapping, virtual_nodes = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
    nodes = [n for n in sorted(expanded_nodes(expanded_edges)) if n in NSFNET_NODES]

    # compute shortest-path distance (meters) between all pairs
    def path_length(src: str, dst: str) -> float:
        path = shortest_path_edges(expanded_edges, src, dst)
        if not path:
            return float("inf")
        return sum(edge[2] for edge in path)

    distances = []
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            src, dst = nodes[i], nodes[j]
            d = path_length(src, dst)
            distances.append((d, src, dst))
    distances.sort(key=lambda x: (-x[0], x[1], x[2]))
    selected = distances[: args.k]

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["src", "dst", "distance_km"])
        for d, s, t in selected:
            writer.writerow([s, t, d / 1000.0])
    print("Selected pairs (src,dst,dist_km):")
    for d, s, t in selected:
        print(f"{s},{t},{d/1000.0:.3f}")
    print(f"Wrote {args.out_csv}")


if __name__ == "__main__":
    main()
