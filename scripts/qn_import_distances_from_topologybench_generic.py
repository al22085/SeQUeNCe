"""Import link distances from a TopologyBench workbook to CSV (generic topology)."""

from __future__ import annotations

import argparse
import csv
import datetime
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert TopologyBench topology distances to CSV.")
    p.add_argument("--xlsx", type=Path, default=None, help="Path to TOP_75_*.xlsx")
    p.add_argument("--zip", type=Path, default=None, help="Path to real_topologies.zip")
    p.add_argument("--topology-id", type=str, required=True, help="Topology id (e.g., NSFNET13)")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("data/topologybench"),
        help="Output directory for distances + provenance",
    )
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
        extracted.rename(out_path)
        return out_path


def main():
    args = parse_args()
    if not args.xlsx and not args.zip:
        raise SystemExit("Provide --xlsx or --zip")
    xlsx = args.xlsx
    if xlsx is None:
        xlsx = find_xlsx_in_zip(args.zip, args.topology_id)
    if not xlsx.exists():
        raise FileNotFoundError(xlsx)

    rows = read_xlsx_rows(xlsx)
    if not rows:
        raise SystemExit("No rows parsed from workbook")
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

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"{args.topology_id}_distances.csv"
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
