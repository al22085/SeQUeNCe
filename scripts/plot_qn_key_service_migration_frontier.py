"""Plot migration frontier curves."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot key-service migration frontier.")
    p.add_argument("--in-agg", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Migration frontier")
    p.add_argument("--use-raw", action="store_true", help="Plot raw frontier instead of monotone envelope.")
    return p.parse_args()


def main():
    args = parse_args()
    data = defaultdict(list)
    with args.in_agg.open() as f:
        reader = csv.DictReader(f)
        use_raw = getattr(args, "use_raw", False)
        for row in reader:
            scenario = row["scenario"]
            strat = row["strategy"]
            lamb = float(row["lambda"])
            frontier = float(row["frontier_rate_bps_raw"] if use_raw else row["frontier_rate_bps"])
            offered = float(row["offered_load_bps"])
            data[scenario].append((strat, lamb, frontier, offered))
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for scenario, vals in data.items():
        grouped = defaultdict(list)
        for strat, lamb, frontier, offered in vals:
            grouped[strat].append((offered, frontier))
        fig, ax = plt.subplots()
        for strat, pts in grouped.items():
            pts.sort(key=lambda x: x[0])
            x = [p[0] for p in pts]
            y = [p[1] for p in pts]
            ax.plot(x, y, marker="o", label=strat)
        ax.set_xlabel("Offered load (bps)")
        ax.set_ylabel("Frontier rate achieving target A")
        ax.set_title(f"{args.title} ({scenario})")
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend()
        fig.tight_layout()
        png = args.out_dir / f"frontier_{scenario}.png"
        pdf = args.out_dir / f"frontier_{scenario}.pdf"
        fig.savefig(png)
        fig.savefig(pdf)
        print(f"Wrote {png}")
        print(f"Wrote {pdf}")


if __name__ == "__main__":
    main()
