"""Export key frontier numbers (BK vs EQT ratios) from ent_frontier_agg.csv."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


def parse_args():
    p = argparse.ArgumentParser(description="Export BK vs EQT frontier ratios.")
    p.add_argument("--in-agg", type=Path, required=True, help="ent_frontier_agg.csv path")
    p.add_argument("--out-csv", type=Path, default=None, help="Optional output CSV")
    return p.parse_args()


def main():
    args = parse_args()
    rows = []
    with args.in_agg.open() as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)

    out_rows = []
    for kbits in (0.5, 1.0):
        for target in (0.9, 0.99, 0.999):
            bk = [r for r in rows if r["strategy"] == "BK" and float(r["kbits"]) == kbits and float(r["target"]) == target and int(float(r["upgrade_k"])) == 0]
            eqt = [r for r in rows if r["strategy"] == "EQT" and float(r["kbits"]) == kbits and float(r["target"]) == target and int(float(r["upgrade_k"])) == 21]
            bk_frontier = float(bk[0]["frontier_load"]) if bk else 0.0
            eqt_frontier = float(eqt[0]["frontier_load"]) if eqt else 0.0
            ratio = eqt_frontier / bk_frontier if bk_frontier > 0 else 0.0
            out_rows.append(
                {
                    "kbits": kbits,
                    "target": target,
                    "bk_frontier": bk_frontier,
                    "eqt_frontier": eqt_frontier,
                    "ratio": ratio,
                    "bk_hits_target": bk_frontier > 0.0,
                }
            )

    if args.out_csv:
        args.out_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.out_csv.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["kbits", "target", "bk_frontier", "eqt_frontier", "ratio", "bk_hits_target"])
            writer.writeheader()
            writer.writerows(out_rows)
        print(f"Wrote {args.out_csv}")
    else:
        for r in out_rows:
            print(r)


if __name__ == "__main__":
    main()
