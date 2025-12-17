"""Plot availability/blocking vs lambda (and Kmax) for key-service sweeps."""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Plot key-service sweep results.")
    p.add_argument("--in-agg", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="Key-service sweep")
    return p.parse_args()


def main():
    args = parse_args()
    data = defaultdict(list)
    with args.in_agg.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            strat = row["strategy"]
            lamb = float(row["lambda"])
            kmax = float(row["kmax"])
            avail = float(row["availability_mean"])
            ci = float(row["availability_ci95"])
            data[(strat, kmax)].append((lamb, avail, ci))
    for vals in data.values():
        vals.sort(key=lambda x: x[0])

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for kmax in sorted({k[1] for k in data.keys()}):
        fig, ax = plt.subplots()
        for strat in sorted({k[0] for k in data.keys() if k[1] == kmax}):
            pts = data[(strat, kmax)]
            lambs = [p[0] for p in pts]
            avails = [p[1] for p in pts]
            err = [p[2] for p in pts]
            ax.errorbar(lambs, avails, yerr=err, marker="o", capsize=3, label=f"{strat}")
        ax.set_xlabel("lambda_req (req/s)")
        ax.set_ylabel("Availability")
        ax.set_title(f"{args.title} (Kmax={kmax})")
        ax.grid(True, linestyle="--", alpha=0.4)
        ax.legend()
        fig.tight_layout()
        png = args.out_dir / f"key_service_kmax_{kmax}.png"
        pdf = args.out_dir / f"key_service_kmax_{kmax}.pdf"
        fig.savefig(png)
        fig.savefig(pdf)
        print(f"Wrote {png}")
        print(f"Wrote {pdf}")


if __name__ == "__main__":
    main()
