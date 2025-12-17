"""Plot eta_crossover vs knob value per distance."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot crossover sensitivity.")
    p.add_argument("--in-csv", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Crossover sensitivity")
    return p.parse_args()


def main():
    args = parse_args()
    data = defaultdict(list)
    with args.in_csv.open() as f:
        reader = csv.DictReader(f)
        knob = None
        for row in reader:
            knob = row["knob"]
            val = float(row["value"])
            dist = float(row["distance"])
            eta = float(row["eta_crossover"])
            data[dist].append((val, eta))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots()
    for dist, vals in sorted(data.items()):
        vals.sort(key=lambda x: x[0])
        xs = [v[0] for v in vals]
        ys = [v[1] for v in vals]
        ax.plot(xs, ys, marker="o", label=f"dist={dist}")
    ax.set_xlabel(f"{knob}")
    ax.set_ylabel("eta_crossover (EQT>=BK)")
    ax.set_title(args.title)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    png = args.out_dir / "crossover_sensitivity.png"
    svg = args.out_dir / "crossover_sensitivity.svg"
    fig.savefig(png)
    fig.savefig(svg)
    print(f"Wrote {png}")
    print(f"Wrote {svg}")


if __name__ == "__main__":
    main()
