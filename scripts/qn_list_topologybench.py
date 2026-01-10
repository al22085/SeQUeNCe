"""List TopologyBench topology stats from XLSX files."""

from __future__ import annotations

import argparse
import csv
import math
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.topologybench_fetch import ensure_topologybench_zip


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "List TopologyBench topologies from XLSX/zip. "
            "Defaults to pinned manifest download into ./data/topologybench/."
        )
    )
    p.add_argument("--xlsx-dir", type=Path, default=None, help="Directory with TOP_75_*.xlsx")
    p.add_argument("--zip", type=Path, default=None, help="Path to real_topologies.zip")
    p.add_argument("--topologybench-zip", type=Path, default=None, help="Alias for --zip.")
    p.add_argument("--out-csv", type=Path, default=None)
    p.add_argument("--manifest", type=Path, default=None, help="Manifest JSON path override.")
    p.add_argument("--no-download", action="store_true", help="Offline mode; do not download.")
    p.add_argument("--no-copy", action="store_true", help="Do not copy a provided zip into ./data/topologybench/.")
    return p.parse_args()


def read_xlsx_rows(xlsx_path: Path, prefer_sheet_contains: list[str] | None = None):
    with zipfile.ZipFile(xlsx_path) as zf:
        shared_strings = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ElementTree.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in root.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si"):
                t = si.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")
                shared_strings.append(t.text if t is not None else "")
        sheet_path = None
        try:
            wb = ElementTree.fromstring(zf.read("xl/workbook.xml"))
            rels = ElementTree.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            rid_to_target = {}
            for r in rels.findall("{http://schemas.openxmlformats.org/package/2006/relationships}Relationship"):
                target = r.attrib["Target"].lstrip("/")
                if not target.startswith("xl/"):
                    target = "xl/" + target
                rid_to_target[r.attrib["Id"]] = target
            sheets = []
            for s in wb.findall("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheets/"
                                "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet"):
                name = s.attrib.get("name", "")
                rid = s.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                sheets.append((name, rid_to_target.get(rid, "")))

            if prefer_sheet_contains:
                for name, path in sheets:
                    lname = name.lower()
                    if any(token.lower() in lname for token in prefer_sheet_contains):
                        sheet_path = path
                        break
            if not sheet_path:
                sheet_path = sheets[0][1] if sheets else "xl/worksheets/sheet1.xml"
        except KeyError:
            sheet_path = "xl/worksheets/sheet1.xml"
        if sheet_path not in zf.namelist():
            sheet_path = [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet")][0]

        root = ElementTree.fromstring(zf.read(sheet_path))
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
    rows = read_xlsx_rows(xlsx_path, prefer_sheet_contains=["edges", "links"])
    if not rows:
        return [], []
    def match_idx(row, keys):
        for i, val in enumerate(row):
            v = str(val).strip().lower()
            for k in keys:
                if v == k or k in v:
                    return i
        return None

    u_idx = v_idx = d_idx = None
    header_row_idx = None
    for idx, row in enumerate(rows):
        u_idx = match_idx(row, ["source", "src", "u", "node1", "node_1", "from", "tail"])
        v_idx = match_idx(row, ["destination", "dst", "v", "node2", "node_2", "to", "head"])
        d_idx = match_idx(
            row,
            [
                "linklengthinkm",
                "distance_km",
                "length_km",
                "linklength",
                "link length",
                "length (km)",
                "length",
                "computed length",
                "distance",
            ],
        )
        if u_idx is not None and v_idx is not None and d_idx is not None:
            header_row_idx = idx
            break
    if header_row_idx is None:
        for idx, row in enumerate(rows):
            if len([x for x in row if str(x).strip()]) >= 4:
                header_row_idx = idx - 1 if idx > 0 else -1
                u_idx, v_idx, d_idx = 1, 2, 3
                break
        if header_row_idx is None:
            return [], []

    edges = []
    nodes = set()
    seen = set()
    for r in rows[header_row_idx + 1:]:
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
        args.zip = ensure_topologybench_zip(
            manifest_path=args.manifest,
            zip_path=args.zip,
            no_download=args.no_download,
            copy_into_data=not args.no_copy,
        )
        with zipfile.ZipFile(args.zip) as zf:
            names = [n for n in zf.namelist() if n.endswith(".xlsx")]
        # extract under data/ for reproducibility
        out_dir = args.zip.parent / "_tb_xlsx_extract"
        if out_dir.exists():
            import shutil
            shutil.rmtree(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.zip) as zf:
            for name in names:
                zf.extract(name, out_dir)
        return sorted(out_dir.rglob("*.xlsx"))
    # fall back to pinned manifest
    zip_path = ensure_topologybench_zip(manifest_path=args.manifest, no_download=args.no_download)
    args.zip = zip_path
    return list_xlsx_paths(args)


def topology_id_from_path(path: Path) -> str:
    name = path.stem
    if name.startswith("TOP_75_"):
        return name.replace("TOP_75_", "")
    return name


def main():
    args = parse_args()
    if args.topologybench_zip and args.zip is None:
        args.zip = args.topologybench_zip
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
