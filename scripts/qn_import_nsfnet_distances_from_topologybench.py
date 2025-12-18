"""Import NSFNET link distances from a TopologyBench workbook."""

from __future__ import annotations

import argparse
import csv
import datetime
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert TopologyBench NSFNET13 distances to CSV.")
    p.add_argument("--real-topologies-zip", type=Path, default=None, help="Path to real_topologies.zip from TopologyBench Zenodo.")
    p.add_argument("--xlsx", type=Path, default=None, help="Path to TOP_75_NSFNET13.xlsx (if already extracted).")
    p.add_argument(
        "--out-csv",
        type=Path,
        default=Path("data/nsfnet_distances_topologybench.csv"),
        help="Output CSV (u,v,distance_km).",
    )
    p.add_argument(
        "--out-md",
        type=Path,
        default=Path("data/nsfnet_distances_topologybench.md"),
        help="Provenance markdown.",
    )
    return p.parse_args()


def extract_xlsx_from_zip(zip_path: Path) -> Path:
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if name.endswith("TOP_75_NSFNET13.xlsx"):
                out_path = zip_path.parent / "TOP_75_NSFNET13.xlsx"
                zf.extract(name, zip_path.parent)
                extracted = zip_path.parent / name
                extracted.rename(out_path)
                return out_path
    raise FileNotFoundError("TOP_75_NSFNET13.xlsx not found in zip")


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


def main():
    args = parse_args()
    xlsx = args.xlsx
    if xlsx is None:
        if not args.real_topologies_zip:
            raise SystemExit("Provide --xlsx or --real-topologies-zip")
        xlsx = extract_xlsx_from_zip(args.real_topologies_zip)
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
    for r in rows[1:]:
        if len(r) <= max(u_idx, v_idx, d_idx):
            continue
        u, v = str(r[u_idx]), str(r[v_idx])
        try:
            d_km = float(r[d_idx])
        except Exception:
            continue
        key = tuple(sorted((u, v)))
        if key not in {(e[0], e[1]) for e in edges}:
            edges.append((key[0], key[1], d_km))

    args.out_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.out_csv.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["u", "v", "distance_km"])
        w.writerows(edges)

    args.out_md.parent.mkdir(parents=True, exist_ok=True)
    provenance = f"""NSFNET distances imported from TopologyBench (Zenodo DOI: 10.5281/zenodo.8202773), file TOP_75_NSFNET13.xlsx.
License: CC BY 4.0 (TopologyBench).
Extraction date: {datetime.date.today().isoformat()}
Columns used: source, destination, linkLengthInKm.
"""
    args.out_md.write_text(provenance)
    print(f"Wrote {args.out_csv}")
    print(f"Wrote {args.out_md}")


if __name__ == "__main__":
    main()
