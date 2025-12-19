"""Plot robustness frontier results across pairs/upgrades/etas."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Plot robustness frontier vs upgrade-k and export key numbers.")
    p.add_argument("--pair-frontier", type=Path, required=True, help="robust_frontier_pairs.csv from robustness runner")
    p.add_argument("--agg", type=Path, required=True, help="robust_frontier_agg.csv from robustness runner")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Robustness frontier")
    return p.parse_args()


def load_csv(path: Path):
    with path.open() as f:
        reader = csv.DictReader(f)
        return list(reader)


def main():
    args = parse_args()
    pair_rows = load_csv(args.pair_frontier)
    agg_rows = load_csv(args.agg)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    etas = sorted({float(r["eta"]) for r in agg_rows})
    targets = sorted({float(r["target"]) for r in agg_rows})
    kbits_vals = sorted({float(r["kbits"]) for r in agg_rows})
    strategies = sorted({r["strategy"] for r in agg_rows})
    upgrade_vals = sorted({int(r["upgrade_k"]) for r in agg_rows})

    # plot frontier_median vs upgrade_k for each eta/target/kbits
    for eta in etas:
        for tgt in targets:
            for kb in kbits_vals:
                plt.figure(figsize=(6, 4))
                for strat in strategies:
                    xs = []
                    ys = []
                    for uk in upgrade_vals:
                        rows = [
                            r
                            for r in agg_rows
                            if float(r["eta"]) == eta
                            and float(r["target"]) == tgt
                            and float(r["kbits"]) == kb
                            and r["strategy"] == strat
                            and int(r["upgrade_k"]) == uk
                        ]
                        if not rows:
                            continue
                        xs.append(uk)
                        ys.append(float(rows[0]["frontier_median"]))
                    if xs:
                        plt.plot(xs, ys, marker="o", label=strat)
                plt.xlabel("upgrade_k (original edges)")
                plt.ylabel("frontier load (lambda)")
                plt.title(f"{args.title}\neta={eta}, target={tgt}, kbits={kb}")
                plt.legend()
                plt.grid(True, alpha=0.3)
                fname = args.out_dir / f"robust_frontier_eta{eta}_t{tgt}_kb{kb}.png"
                plt.tight_layout()
                plt.savefig(fname)
                plt.close()

    # key numbers: median and min ratio EQT/BK using upgrade_k=21 vs 0
    key_rows = []
    for eta in etas:
        for tgt in targets:
            for kb in kbits_vals:
                def get_vals(strat: str, uk: int):
                    return [
                        float(r["frontier_load"])
                        for r in pair_rows
                        if float(r["eta"]) == eta
                        and float(r["target"]) == tgt
                        and float(r["kbits"]) == kb
                        and r["strategy"] == strat
                        and int(r["upgrade_k"]) == uk
                    ]

                bk_vals = get_vals("BK", 0)
                eqt_vals = get_vals("EQT", max(upgrade_vals))
                if not bk_vals or not eqt_vals:
                    continue
                bk_med = float(np.median(bk_vals))
                eqt_med = float(np.median(eqt_vals))
                bk_min = float(np.min(bk_vals))
                eqt_min = float(np.min(eqt_vals))
                ratio_med = eqt_med / bk_med if bk_med > 0 else 0.0
                ratio_min = eqt_min / bk_min if bk_min > 0 else 0.0
                key_rows.append(
                    {
                        "eta": eta,
                        "target": tgt,
                        "kbits": kb,
                        "bk_med": bk_med,
                        "eqt_med": eqt_med,
                        "ratio_med": ratio_med,
                        "bk_min": bk_min,
                        "eqt_min": eqt_min,
                        "ratio_min": ratio_min,
                    }
                )
    key_path = args.out_dir / "robustness_key_numbers.csv"
    with key_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["eta", "target", "kbits", "bk_med", "eqt_med", "ratio_med", "bk_min", "eqt_min", "ratio_min"],
        )
        writer.writeheader()
        writer.writerows(key_rows)
    print(f"Wrote key numbers to {key_path}")


if __name__ == "__main__":
    main()
