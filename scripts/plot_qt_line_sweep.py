"""Plot availability vs distance from aggregated sweep CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot QT line availability curves from aggregated CSV.")
    parser.add_argument("--in-agg", type=Path, required=True, help="Aggregated CSV path (qt_line_agg.csv).")
    parser.add_argument("--out-dir", type=Path, required=True, help="Output directory for figures.")
    parser.add_argument("--title", type=str, default=None, help="Plot title.")
    return parser.parse_args()


def read_agg(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        reader = csv.DictReader(f)
        return list(reader)


def plot_curves(rows: List[Dict[str, str]], out_dir: Path, title: str | None) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))

    strategies = sorted(set(r["strategy"] for r in rows))
    color_map = {"BK": "tab:blue", "DQT": "tab:orange", "EQT": "tab:green"}

    for strat in strategies:
        sr = [r for r in rows if r["strategy"] == strat]
        sr.sort(key=lambda r: float(r["distance"]))
        x = [float(r["distance"]) for r in sr]
        y = [float(r["availability_mean"]) for r in sr]
        ci = [float(r.get("availability_ci95", 0.0) or 0.0) for r in sr]
        ax.errorbar(
            x,
            y,
            yerr=ci,
            label=strat,
            fmt="o-",
            color=color_map.get(strat, None),
            capsize=4,
            markersize=5,
        )

    ax.set_xlabel("Distance (m)")
    ax.set_ylabel("Availability (mean ± CI)")
    if title:
        ax.set_title(title)
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()

    for ext in ("png", "svg"):
        out_path = out_dir / f"qt_line_availability.{ext}"
        fig.savefig(out_path, dpi=200 if ext == "png" else None)
        print("Wrote", out_path)


def main() -> None:
    args = parse_args()
    rows = read_agg(args.in_agg)
    plot_curves(rows, args.out_dir, args.title)


if __name__ == "__main__":
    main()
