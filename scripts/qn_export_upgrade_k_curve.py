"""Export upgrade-k frontier curve metrics (linearity / curvature)."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Export upgrade-k frontier curvature metrics.")
    p.add_argument("--pair-frontier", type=Path, required=True, help="robust_frontier_pairs.csv from robustness run")
    p.add_argument("--out-csv", type=Path, required=True, help="Where to write upgrade_k_curve_numbers.csv")
    p.add_argument("--base-strategy", type=str, default="BK")
    p.add_argument("--curve-strategy", type=str, default="EQT")
    p.add_argument("--target", type=float, default=0.9)
    p.add_argument("--eta", type=float, default=0.9)
    p.add_argument("--kbits", type=float, default=1.0)
    p.add_argument("--upgrade-ks", type=str, default="0,3,7,21")
    return p.parse_args()


def load_rows(path: Path) -> List[Dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def main():
    args = parse_args()
    rows = load_rows(args.pair_frontier)
    ks = [int(x) for x in args.upgrade_ks.split(",") if x]
    ks_sorted = sorted(ks)

    def pick_vals(strategy: str, k: int, pair: Tuple[str, str] | None = None) -> List[float]:
        vals = [
            float(r["frontier_load"])
            for r in rows
            if float(r["eta"]) == args.eta
            and float(r["target"]) == args.target
            and float(r["kbits"]) == args.kbits
            and r["strategy"] == strategy
            and int(r["upgrade_k"]) == k
            and (pair is None or r["pair"] == f"{pair[0]}-{pair[1]}")
        ]
        return vals

    def curve_for_pair(pair: Tuple[str, str]):
        bk0_vals = pick_vals(args.base_strategy, ks_sorted[0], pair)
        if not bk0_vals:
            return None
        bk0 = float(np.median(bk0_vals))
        eqt_vals = {k: pick_vals(args.curve_strategy, k, pair) for k in ks_sorted}
        if any(not v for v in eqt_vals.values()):
            return None
        eqt_frontiers = {k: float(np.median(v)) for k, v in eqt_vals.items()}
        return bk0, eqt_frontiers

    pair_ids = sorted({tuple(r["pair"].split("-")) for r in rows})
    results = []
    for pair in pair_ids:
        curve = curve_for_pair(pair)
        if not curve:
            continue
        bk0, eqt_frontiers = curve
        ratios = {k: (eqt_frontiers[k] / bk0 if bk0 > 0 else 0.0) for k in ks_sorted}
        s03 = (eqt_frontiers.get(3, eqt_frontiers[ks_sorted[0]]) - eqt_frontiers[ks_sorted[0]]) / 3
        s37 = (eqt_frontiers.get(7, eqt_frontiers[3]) - eqt_frontiers.get(3, eqt_frontiers[ks_sorted[0]])) / 4
        s721 = (eqt_frontiers.get(21, eqt_frontiers.get(7, eqt_frontiers[ks_sorted[0]])) - eqt_frontiers.get(7, eqt_frontiers[ks_sorted[0]])) / 14
        results.append(
            {
                "pair": f"{pair[0]}-{pair[1]}",
                "bk0": bk0,
                **{f"eqt{k}": eqt_frontiers[k] for k in ks_sorted},
                **{f"ratio{k}": ratios[k] for k in ks_sorted},
                "s03": s03,
                "s37": s37,
                "s721": s721,
                "c1": s37 - s03,
                "c2": s721 - s37,
            }
        )

    # aggregate median and worst-case (min) across pairs
    def agg_value(key: str, func):
        vals = [r[key] for r in results if key in r]
        return func(vals) if vals else 0.0

    agg_rows = []
    if results:
        for agg_name, func in (("median", np.median), ("worst_case", np.min)):
            row = {"pair": agg_name}
            for key in ["bk0", *(f"eqt{k}" for k in ks_sorted), *(f"ratio{k}" for k in ks_sorted), "s03", "s37", "s721", "c1", "c2"]:
                row[key] = float(func([r[key] for r in results]))
            agg_rows.append(row)

    out_path = args.out_csv
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "pair",
        "bk0",
        *(f"eqt{k}" for k in ks_sorted),
        *(f"ratio{k}" for k in ks_sorted),
        "s03",
        "s37",
        "s721",
        "c1",
        "c2",
    ]
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results + agg_rows:
            writer.writerow(r)
    print(f"Wrote upgrade-k curve numbers to {out_path}")
    if agg_rows:
        print("Aggregated (median/worst_case):")
        for r in agg_rows:
            print(r)


if __name__ == "__main__":
    main()
