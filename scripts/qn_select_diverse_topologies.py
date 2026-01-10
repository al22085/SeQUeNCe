"""Select diverse topologies from TopologyBench listing."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Select diverse topologies by size/diameter/degree.")
    p.add_argument("--list-csv", type=Path, required=True, help="CSV from qn_list_topologybench.py")
    p.add_argument("--k", type=int, default=3)
    p.add_argument("--min-nodes", type=int, default=None)
    p.add_argument("--max-nodes", type=int, default=None)
    p.add_argument("--out-csv", type=Path, default=Path("out/topologybench_selected.csv"))
    return p.parse_args()


def main():
    args = parse_args()
    with args.list_csv.open() as f:
        rows = list(csv.DictReader(f))
    # filter by size
    if args.min_nodes is not None:
        rows = [r for r in rows if int(r["n_nodes"]) >= args.min_nodes]
    if args.max_nodes is not None:
        rows = [r for r in rows if int(r["n_nodes"]) <= args.max_nodes]
    if not rows:
        raise SystemExit("No topologies within size range")

    # select extremes by diameter and degree
    rows_sorted_diam = sorted(rows, key=lambda r: (float(r["diameter_km"]), r["topology_id"]))
    rows_sorted_deg = sorted(rows, key=lambda r: (float(r["avg_degree"]), r["topology_id"]))
    rows_sorted_nodes = sorted(rows, key=lambda r: (int(r["n_nodes"]), r["topology_id"]))
    selected = []
    selected_ids = set()
    def add_row(row):
        if row["topology_id"] not in selected_ids:
            selected.append(row)
            selected_ids.add(row["topology_id"])

    # extremes
    add_row(rows_sorted_diam[0])   # min diameter
    add_row(rows_sorted_diam[-1])  # max diameter
    add_row(rows_sorted_deg[-1])   # max degree
    add_row(rows_sorted_nodes[-1]) # max nodes
    add_row(rows_sorted_nodes[0])  # min nodes

    # fill remaining deterministically by diameter
    for row in rows_sorted_diam:
        if len(selected) >= args.k:
            break
        add_row(row)

    selected = selected[: args.k]

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as f:
        fieldnames = ["topology_id", "n_nodes", "n_edges", "avg_degree", "diameter_km"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in selected:
            writer.writerow({k: row[k] for k in fieldnames})
    print("Selected topologies:")
    for r in selected:
        print(f"{r['topology_id']},{r['n_nodes']},{r['n_edges']},{float(r['avg_degree']):.2f},{float(r['diameter_km']):.2f}")


if __name__ == "__main__":
    main()
