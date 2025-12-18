"""Plot entanglement-service frontier vs upgrade_k and targets."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args():
    p = argparse.ArgumentParser(description="Plot entanglement-service frontier results.")
    p.add_argument("--in-agg", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Entanglement frontier")
    return p.parse_args()


def main():
    args = parse_args()
    data = defaultdict(lambda: defaultdict(list))  # target -> kbits -> list of (upgrade_k, frontier)
    with args.in_agg.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            tgt = float(row["target"])
            kb = float(row["kbits"])
            uk = int(float(row["upgrade_k"]))
            frontier = float(row["frontier_load"])
            strat = row["strategy"]
            data[(tgt, kb, strat)][uk].append(frontier)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for (tgt, kb, strat), uk_map in data.items():
        xs = sorted(uk_map.keys())
        ys = [sum(uk_map[x]) / len(uk_map[x]) for x in xs]
        fig, ax = plt.subplots()
        ax.plot(xs, ys, marker="o")
        ax.set_xlabel("Upgraded edges (k)")
        ax.set_ylabel(f"Frontier load (@A>={tgt})")
        ax.set_title(f"{args.title} {strat} kb={kb} tgt={tgt}")
        ax.grid(True, linestyle="--", alpha=0.4)
        fig.tight_layout()
        suffix = f"{strat}_kb{kb}_t{tgt}".replace(".", "p")
        png = args.out_dir / f"frontier_{suffix}.png"
        pdf = args.out_dir / f"frontier_{suffix}.pdf"
        fig.savefig(png)
        fig.savefig(pdf)
        print(f"Wrote {png}")


if __name__ == "__main__":
    main()
