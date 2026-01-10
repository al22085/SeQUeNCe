"""Select representative pairs by shortest-path distance on original graph."""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import load_edge_distances_csv, build_topology_from_dist_map


def parse_args():
    p = argparse.ArgumentParser(description="Select representative pairs by shortest-path distance.")
    p.add_argument("--edge-distance-csv", type=Path, required=True)
    p.add_argument("--topology-id", type=str, required=True)
    p.add_argument("--targets-km", type=str, default="404,511,1002")
    p.add_argument("--pairs-per-target", type=int, default=1)
    p.add_argument("--out-csv", type=Path, required=True)
    return p.parse_args()


def parse_list(raw: str) -> List[float]:
    return [float(x) for x in raw.split(",") if x]


def dijkstra(topo: Dict[str, List[str]], dist: Dict[Tuple[str, str], float], src: str) -> Dict[str, float]:
    import heapq

    pq = [(0.0, src)]
    best = {src: 0.0}
    while pq:
        d, n = heapq.heappop(pq)
        if d > best[n]:
            continue
        for nei in topo[n]:
            key = tuple(sorted((n, nei)))
            w = dist[key]
            nd = d + w
            if nei not in best or nd < best[nei]:
                best[nei] = nd
                heapq.heappush(pq, (nd, nei))
    return best


def main():
    args = parse_args()
    dist_m = load_edge_distances_csv(args.edge_distance_csv)
    topo = build_topology_from_dist_map(dist_m)
    nodes = sorted(topo.keys())
    targets = parse_list(args.targets_km)

    # all-pairs shortest-path distances (km)
    pairs = []
    for i in range(len(nodes)):
        src = nodes[i]
        best = dijkstra(topo, dist_m, src)
        for j in range(i + 1, len(nodes)):
            dst = nodes[j]
            if dst not in best:
                continue
            pairs.append((best[dst] / 1000.0, src, dst))

    selected = []
    used = set()
    labels = ["short", "medium", "long"]
    for idx, target in enumerate(targets):
        candidates = []
        for sp_km, s, t in pairs:
            if (s, t) in used:
                continue
            err = abs(sp_km - target)
            candidates.append((err, sp_km, s, t))
        candidates.sort(key=lambda x: (x[0], x[2], x[3]))
        label_base = labels[idx] if idx < len(labels) else f"target_{target}"
        for pick_idx, c in enumerate(candidates[: args.pairs_per_target], start=1):
            used.add((c[2], c[3]))
            label = label_base if args.pairs_per_target == 1 else f"{label_base}_{pick_idx}"
            selected.append((label, c[2], c[3], c[1], target, c[0]))

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["label", "src_node", "dst_node", "sp_km", "target_km", "abs_error_km"])
        for row in selected:
            w.writerow(row)
    print(f"Wrote {args.out_csv}")


if __name__ == "__main__":
    main()
