"""Plot availability vs deadline_factor from calibration agg CSV."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot availability vs deadline_factor.")
    p.add_argument("--in-agg", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Deadline factor calibration")
    return p.parse_args()


def read_agg(path: Path):
    data = defaultdict(list)
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = f"{row['arch']}-{row['strategy']}"
            data[key].append(
                (
                    float(row["factor"]),
                    float(row["availability_mean"]),
                    float(row["availability_ci95"]),
                )
            )
    for vals in data.values():
        vals.sort(key=lambda x: x[0])
    return data


def main():
    args = parse_args()
    series = read_agg(args.in_agg)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots()
    for label, vals in series.items():
        xs = [v[0] for v in vals]
        ys = [v[1] for v in vals]
        err = [v[2] for v in vals]
        ax.errorbar(xs, ys, yerr=err, marker="o", capsize=3, label=label)
    ax.set_xscale("log")
    ax.set_xlabel("deadline_factor")
    ax.set_ylabel("availability_req")
    ax.set_title(args.title)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    png = args.out_dir / "deadline_calibration.png"
    svg = args.out_dir / "deadline_calibration.svg"
    fig.savefig(png)
    fig.savefig(svg)
    print(f"Wrote {png}")
    print(f"Wrote {svg}")


if __name__ == "__main__":
    main()
