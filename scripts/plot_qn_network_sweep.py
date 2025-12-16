"""Plot availability vs distance from qn_network_sweep agg CSV."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot availability vs distance from sweep CSV.")
    p.add_argument("--in-agg", type=Path, required=True, help="Aggregated CSV from qn_network_sweep.py")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Network availability sweep")
    return p.parse_args()


def read_agg(path: Path):
    series = defaultdict(list)
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            arch = row["arch"]
            strat = row["strategy"]
            key = f"{arch}-{strat}"
            series[key].append(
                (
                    float(row["distance"]),
                    float(row["availability_mean"]),
                    float(row["availability_ci95"]),
                )
            )
    for vals in series.values():
        vals.sort(key=lambda x: x[0])
    return series


def main():
    args = parse_args()
    series = read_agg(args.in_agg)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots()
    for label, points in series.items():
        dist = [p[0] for p in points]
        mean = [p[1] for p in points]
        err = [p[2] for p in points]
        ax.errorbar(dist, mean, yerr=err, marker="o", capsize=3, label=label)

    ax.set_xlabel("Distance per link (m)")
    ax.set_ylabel("Availability_req")
    ax.set_title(args.title)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()

    png = args.out_dir / "qn_network_sweep.png"
    svg = args.out_dir / "qn_network_sweep.svg"
    fig.tight_layout()
    fig.savefig(png)
    fig.savefig(svg)
    print(f"Wrote {png}")
    print(f"Wrote {svg}")


if __name__ == "__main__":
    main()
