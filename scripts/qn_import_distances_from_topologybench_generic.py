"""Import link distances from a TopologyBench workbook to CSV (generic topology)."""

from __future__ import annotations

import argparse
import csv
import datetime
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.topologybench_fetch import ensure_topologybench_zip


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Convert TopologyBench topology distances to CSV. "
            "Defaults to pinned manifest download into ./data/topologybench/."
        )
    )
    p.add_argument("--xlsx", type=Path, default=None, help="Path to TOP_75_*.xlsx")
    p.add_argument("--zip", type=Path, default=None, help="Path to real_topologies.zip (will be copied into ./data/).")
    p.add_argument("--topologybench-zip", type=Path, default=None, help="Alias for --zip.")
    p.add_argument("--topology-id", type=str, required=True, help="Topology id (e.g., NSFNET13)")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/topologybench_distances"),
        help="Output directory for distances + provenance",
    )
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


def find_xlsx_in_zip(zip_path: Path, topology_id: str) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        candidates = [n for n in zf.namelist() if n.endswith(".xlsx") and topology_id.lower() in n.lower()]
        if not candidates:
            raise FileNotFoundError(f"No XLSX for {topology_id} in {zip_path}")
        if len(candidates) > 1:
            raise FileExistsError(f"Multiple XLSX candidates for {topology_id}: {candidates}")
        out_path = zip_path.parent / Path(candidates[0]).name
        zf.extract(candidates[0], zip_path.parent)
        extracted = zip_path.parent / candidates[0]
        try:
            extracted.rename(out_path)
        except OSError:
            import shutil
            shutil.move(str(extracted), str(out_path))
        return out_path


def main():
    args = parse_args()
    if args.topologybench_zip and args.zip is None:
        args.zip = args.topologybench_zip
    if not args.xlsx:
        args.zip = ensure_topologybench_zip(
            manifest_path=args.manifest,
            zip_path=args.zip,
            no_download=args.no_download,
            copy_into_data=not args.no_copy,
        )
    xlsx = args.xlsx
    if xlsx is None:
        xlsx = find_xlsx_in_zip(args.zip, args.topology_id)
    if not xlsx.exists():
        raise FileNotFoundError(xlsx)

    rows = read_xlsx_rows(xlsx, prefer_sheet_contains=["edges", "links"])
    if not rows:
        raise SystemExit("No rows parsed from workbook")
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
        # fallback: assume columns [id, source, destination, linkLengthInKm]
        for idx, row in enumerate(rows):
            if len([x for x in row if str(x).strip()]) >= 4:
                header_row_idx = idx - 1 if idx > 0 else -1
                u_idx, v_idx, d_idx = 1, 2, 3
                break
        if header_row_idx is None:
            raise SystemExit("Expected columns source/destination (or u/v) and distance in XLSX")

    edges = []
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

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"{args.topology_id}.csv"
    out_md = out_dir / f"{args.topology_id}_provenance.md"

    with out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["u", "v", "linkLengthInKm"])
        w.writerows(edges)

    provenance = f"""Topology distances imported from TopologyBench (Zenodo DOI: 10.5281/zenodo.8202773).
License: CC BY 4.0 (TopologyBench).
Topology id: {args.topology_id}
Source workbook: {xlsx.name}
Extraction date: {datetime.date.today().isoformat()}
Columns used: source, destination, linkLengthInKm.
"""
    out_md.write_text(provenance)
    print(f"Wrote {out_csv}")
    print(f"Wrote {out_md}")


if __name__ == "__main__":
    main()
