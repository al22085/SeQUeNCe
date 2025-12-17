"""Plot phase sweep results (distance x eta) and EQT-BK difference."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot distance x eta phase sweep.")
    p.add_argument("--in-agg", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Phase sweep (hybrid)")
    return p.parse_args()


def read_agg(path: Path):
    data = defaultdict(list)
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            dist = float(row["distance"])
            eta = float(row["eta"])
            strat = row["strategy"]
            mean = float(row["availability_mean"])
            ci = float(row["availability_ci95"])
            data[(eta, strat)].append((dist, mean, ci))
    for vals in data.values():
        vals.sort(key=lambda x: x[0])
    return data


def plot_availability(data, out_dir: Path, title: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots()
    labels = []
    for (eta, strat), vals in sorted(data.items()):
        dist = [v[0] for v in vals]
        mean = [v[1] for v in vals]
        err = [v[2] for v in vals]
        lbl = f"{strat}-eta{eta}"
        labels.append(lbl)
        ax.errorbar(dist, mean, yerr=err, marker="o", capsize=3, label=lbl)
    ax.set_xlabel("Distance per link (m)")
    ax.set_ylabel("Availability_req")
    ax.set_title(title)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    png = out_dir / "phase_availability.png"
    svg = out_dir / "phase_availability.svg"
    fig.savefig(png)
    fig.savefig(svg)
    print(f"Wrote {png}")
    print(f"Wrote {svg}")


def plot_diff(data, out_dir: Path):
    # compute EQT - BK difference per eta
    diff_lines = defaultdict(list)
    for eta in {k[0] for k in data.keys()}:
        bk = {d: m for d, m, _ in data.get((eta, "BK"), [])}
        eqt = {d: m for d, m, _ in data.get((eta, "EQT"), [])}
        common = sorted(set(bk.keys()) & set(eqt.keys()))
        for d in common:
            diff_lines[eta].append((d, eqt[d] - bk[d]))
    fig, ax = plt.subplots()
    for eta, vals in sorted(diff_lines.items()):
        dist = [v[0] for v in vals]
        diff = [v[1] for v in vals]
        ax.plot(dist, diff, marker="o", label=f"eta{eta}")
    ax.axhline(0, color="k", linestyle="--", alpha=0.5)
    ax.set_xlabel("Distance per link (m)")
    ax.set_ylabel("EQT - BK availability")
    ax.set_title("EQT advantage vs BK")
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    png = out_dir / "phase_diff.png"
    svg = out_dir / "phase_diff.svg"
    fig.savefig(png)
    fig.savefig(svg)
    print(f"Wrote {png}")
    print(f"Wrote {svg}")


def main():
    args = parse_args()
    data = read_agg(args.in_agg)
    plot_availability(data, args.out_dir, args.title)
    plot_diff(data, args.out_dir)


if __name__ == "__main__":
    main()
