"""Plot phase sweep results (distance x eta) and EQT-BK difference."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot distance x eta phase sweep.")
    p.add_argument("--in-agg", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Phase sweep (hybrid)")
    return p.parse_args()


def read_agg(path: Path):
    data = defaultdict(list)
    bk_map = defaultdict(dict)
    eqt_map = defaultdict(dict)
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            dist = float(row["distance"])
            eta = float(row["eta"])
            strat = row["strategy"]
            mean = float(row["availability_mean"])
            ci = float(row["availability_ci95"])
            data[(eta, strat)].append((dist, mean, ci))
            if strat == "BK":
                bk_map[eta][dist] = mean
            if strat == "EQT":
                eqt_map[eta][dist] = mean
    for vals in data.values():
        vals.sort(key=lambda x: x[0])
    return data, bk_map, eqt_map


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
    data, bk_map, eqt_map = read_agg(args.in_agg)
    plot_availability(data, args.out_dir, args.title)
    plot_diff(data, args.out_dir)

    # Heatmaps for BK, EQT, and diff
    def heatmap_for(strat_map, name):
        etas = sorted(strat_map.keys())
        dists = sorted({d for emap in strat_map.values() for d in emap.keys()})
        grid = np.zeros((len(etas), len(dists)))
        for i, e in enumerate(etas):
            for j, d in enumerate(dists):
                grid[i, j] = strat_map[e].get(d, np.nan)
        fig, ax = plt.subplots()
        c = ax.pcolormesh(dists, etas, grid, shading="auto", cmap="viridis")
        fig.colorbar(c, ax=ax, label="availability")
        ax.set_xlabel("Distance per link (m)")
        ax.set_ylabel("Eta")
        ax.set_title(f"{name} availability heatmap")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        png = args.out_dir / f"{name.lower()}_heatmap.png"
        svg = args.out_dir / f"{name.lower()}_heatmap.svg"
        fig.tight_layout()
        fig.savefig(png)
        fig.savefig(svg)
        print(f"Wrote {png}")
        print(f"Wrote {svg}")
        return etas, dists, grid

    _, _, _ = heatmap_for(bk_map, "BK")
    etas, dists, eqt_grid = heatmap_for(eqt_map, "EQT")
    # diff heatmap
    diff_map = defaultdict(dict)
    for e in etas:
        for d in dists:
            diff_map[e][d] = eqt_map.get(e, {}).get(d, np.nan) - bk_map.get(e, {}).get(d, np.nan)
    _, _, diff_grid = heatmap_for(diff_map, "EQT_minus_BK")

    # crossover extraction
    rows = []
    for d in dists:
        eta_vals = sorted(etas)
        bk_vals = [bk_map.get(e, {}).get(d, np.nan) for e in eta_vals]
        eqt_vals = [eqt_map.get(e, {}).get(d, np.nan) for e in eta_vals]
        crossover = None
        for i, e in enumerate(eta_vals):
            diff = eqt_vals[i] - bk_vals[i]
            if np.isnan(diff):
                continue
            if diff >= 0:
                if i == 0:
                    crossover = (e, diff)
                else:
                    prev_diff = eqt_vals[i - 1] - bk_vals[i - 1]
                    prev_eta = eta_vals[i - 1]
                    if np.isnan(prev_diff):
                        crossover = (e, diff)
                    else:
                        # linear interpolation
                        if diff == prev_diff:
                            eta_cross = e
                        else:
                            eta_cross = prev_eta + (e - prev_eta) * (-prev_diff) / (diff - prev_diff)
                        crossover = (eta_cross, diff)
                break
        if crossover is not None:
            rows.append((d, crossover[0], crossover[1]))
        else:
            rows.append((d, np.nan, np.nan))
    cross_path = args.out_dir / "phase_crossover.csv"
    with cross_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["distance", "eta_crossover", "diff_at_crossover"])
        writer.writerows(rows)
    print(f"Wrote {cross_path}")


if __name__ == "__main__":
    main()
