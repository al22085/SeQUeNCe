"""Plot upgrade-k threshold mechanism and export key numbers."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt
import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Plot upgrade threshold mechanism and export key numbers.")
    p.add_argument("--coverage-csv", type=Path, required=True)
    p.add_argument("--frontier-pairs", type=Path, required=True)
    p.add_argument("--longpair-summary", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--eta", type=float, default=0.9)
    p.add_argument("--target", type=float, default=0.9)
    p.add_argument("--kbits", type=float, default=1.0)
    p.add_argument("--title", type=str, default="Upgrade threshold mechanism")
    return p.parse_args()


def load_rows(path: Path) -> List[Dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def main():
    args = parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    coverage = load_rows(args.coverage_csv)
    frontier = load_rows(args.frontier_pairs)
    long_summary = load_rows(args.longpair_summary)

    # Plot 1: upgrade_k vs path_upgraded_fraction per pair
    pairs = sorted({r["pair"] for r in coverage})
    upgrade_vals = sorted({int(r["upgrade_k"]) for r in coverage})
    plt.figure(figsize=(6, 4))
    for pair in pairs:
        xs, ys = [], []
        for uk in upgrade_vals:
            rows = [r for r in coverage if r["pair"] == pair and int(r["upgrade_k"]) == uk]
            if not rows:
                continue
            xs.append(uk)
            ys.append(float(rows[0]["path_upgraded_fraction"]))
        if xs:
            plt.plot(xs, ys, marker="o", label=pair)
    plt.xlabel("upgrade_k (original edges)")
    plt.ylabel("path upgraded fraction")
    plt.title(f"{args.title}\nShortest-path coverage")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(args.out_dir / "upgrade_k_path_coverage.png")
    plt.close()

    # Plot 2: upgrade_k vs frontier (median across pairs)
    filtered_frontier = [
        r
        for r in frontier
        if float(r["eta"]) == args.eta
        and float(r["target"]) == args.target
        and float(r["kbits"]) == args.kbits
    ]
    strategies = sorted({r["strategy"] for r in filtered_frontier})
    plt.figure(figsize=(6, 4))
    for strat in strategies:
        xs, ys = [], []
        for uk in upgrade_vals:
            vals = [
                float(r["frontier_load"])
                for r in filtered_frontier
                if r["strategy"] == strat and int(r["upgrade_k"]) == uk
            ]
            if not vals:
                continue
            xs.append(uk)
            ys.append(float(np.median(vals)))
        if xs:
            plt.plot(xs, ys, marker="o", label=strat)
    plt.xlabel("upgrade_k (original edges)")
    plt.ylabel("frontier load (median)")
    plt.title(f"{args.title}\nFrontier vs upgrade_k")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(args.out_dir / "upgrade_k_frontier_median.png")
    plt.close()

    # Plot 3: ratio vs coverage fraction (scatter)
    ratio_rows = []
    bk0_vals = [
        float(r["frontier_load"])
        for r in filtered_frontier
        if r["strategy"] == "BK" and int(r["upgrade_k"]) == 0
    ]
    bk0 = float(np.median(bk0_vals)) if bk0_vals else 0.0
    if bk0 > 0:
        for r in filtered_frontier:
            if r["strategy"] != "EQT":
                continue
            cov = [
                c
                for c in coverage
                if c["pair"] == r["pair"] and int(c["upgrade_k"]) == int(r["upgrade_k"])
            ]
            if not cov:
                continue
            ratio_rows.append(
                (
                    float(cov[0]["path_upgraded_fraction"]),
                    float(r["frontier_load"]) / bk0,
                )
            )
    if ratio_rows:
        xs, ys = zip(*ratio_rows)
        plt.figure(figsize=(6, 4))
        plt.scatter(xs, ys, alpha=0.8)
        plt.xlabel("path upgraded fraction")
        plt.ylabel("EQT/BK0 frontier ratio")
        plt.title(f"{args.title}\nRatio vs path coverage")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(args.out_dir / "ratio_vs_path_coverage.png")
        plt.close()

    # Plot 4: long-pair counters vs upgrade_k
    long_rows = [
        r for r in long_summary
        if float(r["eta"]) == args.eta and float(r["load"]) == float(long_summary[0]["load"])
    ]
    if long_rows:
        plt.figure(figsize=(6, 4))
        for metric in ["mem_expired_mean", "swap_fail_rate_mean", "delivered_pairs_mean"]:
            xs, ys = [], []
            for uk in upgrade_vals:
                vals = [
                    float(r[metric])
                    for r in long_rows
                    if r["strategy"] == "EQT" and int(r["upgrade_k"]) == uk
                ]
                if not vals:
                    continue
                xs.append(uk)
                ys.append(float(np.mean(vals)))
            if xs:
                plt.plot(xs, ys, marker="o", label=metric)
        plt.xlabel("upgrade_k (original edges)")
        plt.ylabel("long-pair counters (mean)")
        plt.title(f"{args.title}\nLong-pair counters vs k")
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.savefig(args.out_dir / "longpair_counters_vs_k.png")
        plt.close()

    # Key numbers table
    key_rows = []
    for uk in upgrade_vals:
        cov = [
            c
            for c in coverage
            if c.get("label") == "long" and int(c["upgrade_k"]) == uk
        ]
        if not cov:
            continue
        eqt_vals = [
            float(r["frontier_load"])
            for r in filtered_frontier
            if r["strategy"] == "EQT" and int(r["upgrade_k"]) == uk
        ]
        bk_vals = [
            float(r["frontier_load"])
            for r in filtered_frontier
            if r["strategy"] == "BK" and int(r["upgrade_k"]) == 0
        ]
        if not eqt_vals or not bk_vals:
            continue
        eqt_med = float(np.median(eqt_vals))
        bk_med = float(np.median(bk_vals))
        ratio = eqt_med / bk_med if bk_med > 0 else 0.0
        long_stats = [
            r for r in long_summary
            if r["strategy"] == "EQT" and int(r["upgrade_k"]) == uk
        ]
        mem_expired_mean = float(np.mean([float(r["mem_expired_mean"]) for r in long_stats])) if long_stats else 0.0
        swap_fail_rate_mean = float(np.mean([float(r["swap_fail_rate_mean"]) for r in long_stats])) if long_stats else 0.0
        key_rows.append(
            {
                "upgrade_k": uk,
                "path_upgraded_fraction_longpair": cov[0]["path_upgraded_fraction"],
                "longest_run_longpair": cov[0]["longest_consecutive_upgraded_run"],
                "EQT_frontier_median": eqt_med,
                "BK0_frontier_median": bk_med,
                "ratio_median": ratio,
                "mem_expired_mean_longpair": mem_expired_mean,
                "swap_fail_rate_mean_longpair": swap_fail_rate_mean,
            }
        )

    key_path = args.out_dir / "threshold_mechanism_key_numbers.csv"
    with key_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "upgrade_k",
                "path_upgraded_fraction_longpair",
                "longest_run_longpair",
                "EQT_frontier_median",
                "BK0_frontier_median",
                "ratio_median",
                "mem_expired_mean_longpair",
                "swap_fail_rate_mean_longpair",
            ],
        )
        writer.writeheader()
        writer.writerows(key_rows)
    print(f"Wrote {key_path}")

    if key_rows:
        print("Interpretation: look for flat coverage/ratio at low k and jumps at k=21.")


if __name__ == "__main__":
    main()
