"""List TopologyBench topology stats from XLSX files."""

from __future__ import annotations

import argparse
import csv
import math
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def parse_args():
    p = argparse.ArgumentParser(description="List TopologyBench topologies from XLSX/zip.")
    p.add_argument("--xlsx-dir", type=Path, default=None, help="Directory with TOP_75_*.xlsx")
    p.add_argument("--zip", type=Path, default=None, help="Path to real_topologies.zip")
    p.add_argument("--out-csv", type=Path, default=None)
    return p.parse_args()


def read_xlsx_rows(xlsx_path: Path):
    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                t = si.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                shared_strings.append(t.text if t is not None else "")
        sheet_name = "xl/worksheets/sheet1.xml"
        if sheet_name not in zf.namelist():
            sheet_name = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet")][0]
        root = ElementTree.fromstring(zf.read(sheet_name))
        rows = []
        for row in root.iter("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"):
            vals = []
            for c in row.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c"):
                t = c.get("t")
                v = c.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v")
                if v is None:
                    vals.append("")
                    continue
                if t == "s":
                    idx = int(v.text)
                    vals.append(shared_strings[idx])
                else:
                    vals.append(v.text)
            rows.append(vals)
    return rows


def parse_edges(xlsx_path: Path):
    rows = read_xlsx_rows(xlsx_path)
    if not rows:
        return [], []
    header = [h.lower() for h in rows[0]]
    try:
        u_idx = header.index("source")
        v_idx = header.index("destination")
    except ValueError:
        try:
            u_idx = header.index("u")
            v_idx = header.index("v")
        except ValueError:
            raise SystemExit("Expected columns source/destination (or u/v)")
    try:
        d_idx = header.index("linklengthinkm")
    except ValueError:
        try:
            d_idx = header.index("distance_km")
        except ValueError:
            raise SystemExit("Expected distance column (linkLengthInKm or distance_km)")

    edges = []
    nodes = set()
    seen = set()
    for r in rows[1:]:
        if len(r) <= max(u_idx, v_idx, d_idx):
            continue
        u, v = str(r[u_idx]), str(r[v_idx])
        try:
            d_km = float(r[d_idx])
        except Exception:
            continue
        key = tuple(sorted((u, v)))
        if key in seen:
            continue
        seen.add(key)
        edges.append((key[0], key[1], d_km))
        nodes.add(key[0])
        nodes.add(key[1])
    return nodes, edges


def dijkstra(adj, src):
    import heapq
    dist = {src: 0.0}
    pq = [(0.0, src)]
    while pq:
        d, n = heapq.heappop(pq)
        if d > dist[n]:
            continue
        for nei, w in adj.get(n, []):
            nd = d + w
            if nei not in dist or nd < dist[nei]:
                dist[nei] = nd
                heapq.heappush(pq, (nd, nei))
    return dist


def compute_diameter(nodes, edges):
    adj = {}
    for u, v, w in edges:
        adj.setdefault(u, []).append((v, w))
        adj.setdefault(v, []).append((u, w))
    max_d = 0.0
    for n in nodes:
        dist = dijkstra(adj, n)
        if dist:
            max_d = max(max_d, max(dist.values()))
    return max_d


def list_xlsx_paths(args):
    if args.xlsx_dir:
        return sorted([p for p in args.xlsx_dir.glob("*.xlsx")])
    if args.zip:
        with zipfile.ZipFile(args.zip) as zf:
            names = [n for n in zf.namelist() if n.endswith(".xlsx")]
        # extract to temp dir under zip parent
        out_dir = args.zip.parent / "_tb_xlsx_extract"
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.zip) as zf:
            for name in names:
                zf.extract(name, out_dir)
        return sorted(out_dir.glob("*.xlsx"))
    raise SystemExit("Provide --xlsx-dir or --zip")


def topology_id_from_path(path: Path) -> str:
    name = path.stem
    if name.startswith("TOP_75_"):
        return name.replace("TOP_75_", "")
    return name


def main():
    args = parse_args()
    rows = []
    for xlsx in list_xlsx_paths(args):
        topo_id = topology_id_from_path(xlsx)
        nodes, edges = parse_edges(xlsx)
        if not nodes:
            continue
        n_nodes = len(nodes)
        n_edges = len(edges)
        avg_degree = (2 * n_edges / n_nodes) if n_nodes else 0.0
        diameter_km = compute_diameter(nodes, edges)
        rows.append(
            {
                "topology_id": topo_id,
                "n_nodes": n_nodes,
                "n_edges": n_edges,
                "avg_degree": avg_degree,
                "diameter_km": diameter_km,
            }
        )

    if args.out_csv:
        with args.out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["topology_id", "n_nodes", "n_edges", "avg_degree", "diameter_km"],
            )
            writer.writeheader()
            writer.writerows(rows)
    for r in rows:
        print(f"{r['topology_id']},{r['n_nodes']},{r['n_edges']},{r['avg_degree']:.2f},{r['diameter_km']:.2f}")


if __name__ == "__main__":
    main()
