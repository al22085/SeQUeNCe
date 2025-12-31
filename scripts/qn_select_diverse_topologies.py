"""Select diverse topologies from TopologyBench listing."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Select diverse topologies by size/diameter/degree.")
    p.add_argument("--list-csv", type=Path, required=True, help="CSV from qn_list_topologybench.py")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--min-nodes", type=int, default=10)
    p.add_argument("--max-nodes", type=int, default=30)
    p.add_argument("--out-csv", type=Path, default=Path("out/topologybench_selected.csv"))
    return p.parse_args()


def main():
    args = parse_args()
    with args.list_csv.open() as f:
        rows = list(csv.DictReader(f))
    # filter by size
    rows = [r for r in rows if args.min_nodes <= int(r["n_nodes"]) <= args.max_nodes]
    if not rows:
        raise SystemExit("No topologies within size range")

    # select extremes by diameter and degree
    rows_sorted_diam = sorted(rows, key=lambda r: float(r["diameter_km"]))
    rows_sorted_deg = sorted(rows, key=lambda r: float(r["avg_degree"]))
    selected = []
    # min diameter
    selected.append(rows_sorted_diam[0])
    # max diameter
    if rows_sorted_diam[-1]["topology_id"] not in {r["topology_id"] for r in selected}:
        selected.append(rows_sorted_diam[-1])
    # max degree
    if rows_sorted_deg[-1]["topology_id"] not in {r["topology_id"] for r in selected}:
        selected.append(rows_sorted_deg[-1])
    # fill remaining by median diameter
    if len(selected) < args.k:
        mid = rows_sorted_diam[len(rows_sorted_diam) // 2]
        if mid["topology_id"] not in {r["topology_id"] for r in selected}:
            selected.append(mid)
    selected = selected[: args.k]

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["topology_id", "n_nodes", "n_edges", "avg_degree", "diameter_km"],
        )
        writer.writeheader()
        writer.writerows(selected)
    print("Selected topologies:")
    for r in selected:
        print(f"{r['topology_id']},{r['n_nodes']},{r['n_edges']},{float(r['avg_degree']):.2f},{float(r['diameter_km']):.2f}")


if __name__ == "__main__":
    main()
