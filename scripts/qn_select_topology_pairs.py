"""Select representative pairs for a generic topology from an edge CSV."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import (
    load_graph_from_edge_csv,
    subdivide_edges,
    shortest_path_edges,
)


def parse_args():
    p = argparse.ArgumentParser(description="Select representative pairs for a generic topology.")
    p.add_argument("--edge-distance-csv", type=Path, required=True)
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--mode", choices=["longest", "shortest", "extremes", "literature_anchored"], default="literature_anchored")
    p.add_argument("--k", type=int, default=5)
    p.add_argument("--target-km-list", type=str, default="404,511,1002")
    p.add_argument("--out-csv", type=Path, default=Path("out/topology_pairs.csv"))
    return p.parse_args()


def main():
    args = parse_args()
    topo, dist_map = load_graph_from_edge_csv(args.edge_distance_csv)
    expanded_edges, _, _ = subdivide_edges(dist_map, segment_length_km=args.segment_length_km)
    nodes = sorted(topo.keys())

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

    if args.mode == "shortest":
        distances.sort(key=lambda x: (x[0], x[1], x[2]))
        selected = distances[: args.k]
    elif args.mode == "extremes":
        distances.sort(key=lambda x: (x[0], x[1], x[2]))
        shortest = distances[: args.k]
        distances.sort(key=lambda x: (-x[0], x[1], x[2]))
        longest = distances[: args.k]
        selected = shortest + longest
    elif args.mode == "literature_anchored":
        targets = [float(t) for t in args.target_km_list.split(",") if t]
        selected = []
        used = set()
        for target in targets:
            best = None
            for d, s, t in distances:
                if (s, t) in used:
                    continue
                err = abs(d / 1000.0 - target)
                if best is None or err < best[0] or (err == best[0] and (s, t) < (best[1], best[2])):
                    best = (err, s, t, d / 1000.0, target)
            if best:
                used.add((best[1], best[2]))
                used.add((best[2], best[1]))
                selected.append(best)
        selected = [(b[3], b[1], b[2], b[4], b[0]) for b in selected]
    else:
        distances.sort(key=lambda x: (-x[0], x[1], x[2]))
        selected = distances[: args.k]

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as f:
        writer = csv.writer(f)
        if args.mode == "literature_anchored":
            writer.writerow(["label", "src", "dst", "distance_km", "target_km", "abs_error_km"])
            labels = ["short", "medium", "long"]
            for idx, row in enumerate(selected):
                dist_km, s, t, target_km, err = row
                label = labels[idx] if idx < len(labels) else f"target_{target_km}"
                writer.writerow([label, s, t, dist_km, target_km, err])
            print("Selected pairs (label,src,dst,dist_km,target_km,abs_error_km):")
            for idx, row in enumerate(selected):
                dist_km, s, t, target_km, err = row
                label = labels[idx] if idx < len(labels) else f"target_{target_km}"
                print(f"{label},{s},{t},{dist_km:.3f},{target_km:.3f},{err:.3f}")
        else:
            writer.writerow(["src", "dst", "distance_km"])
            for d, s, t in selected:
                writer.writerow([s, t, d / 1000.0])
            print("Selected pairs (src,dst,dist_km):")
            for d, s, t in selected:
                print(f"{s},{t},{d/1000.0:.3f}")
    print(f"Wrote {args.out_csv}")


if __name__ == "__main__":
    main()
