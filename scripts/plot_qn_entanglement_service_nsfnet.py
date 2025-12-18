"""Plot NSFNET entanglement-service availability for BK vs EQT."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List

import matplotlib.pyplot as plt


def parse_args():
    p = argparse.ArgumentParser(description="Plot entanglement service availability for NSFNET runs.")
    p.add_argument("--summary-paths", type=str, required=True, help="Comma list of summary.json paths.")
    p.add_argument("--labels", type=str, default="", help="Comma list of labels matching summaries (fallback: strategy).")
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--title", type=str, default="NSFNET entanglement service")
    return p.parse_args()


def main():
    args = parse_args()
    paths = [Path(p) for p in args.summary_paths.split(",") if p]
    labels = [l for l in args.labels.split(",") if l]
    args.out_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots()
    xs = []
    ys = []
    for idx, p in enumerate(paths):
        data = json.loads(p.read_text())
        label = labels[idx] if idx < len(labels) else data.get("strategy", p.parent.parent.name)
        kb = data.get("key_bits_per_pair", 1.0)
        xs.append(f"{label}\nkb={kb}")
        ys.append(data["availability_mean"])
    ax.bar(xs, ys)
    ax.set_ylabel("Availability")
    ax.set_ylim(0, 1)
    ax.set_title(args.title)
    fig.tight_layout()
    png = args.out_dir / "entanglement_service_nsfnet.png"
    pdf = args.out_dir / "entanglement_service_nsfnet.pdf"
    fig.savefig(png)
    fig.savefig(pdf)
    print(f"Wrote {png}")
    print(f"Wrote {pdf}")


if __name__ == "__main__":
    main()
