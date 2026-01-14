#!/usr/bin/env python3
"""Plot consolidated availability artifacts from results_agg.csv."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot paper artifacts from results_agg.csv.")
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("out/paper_artifacts/results_agg.csv"),
        help="Path to results_agg.csv.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("out/paper_artifacts/figures"),
        help="Output directory for figures.",
    )
    parser.add_argument(
        "--study",
        type=str,
        default="study_upgrade_k",
        help="Study name to plot (default: study_upgrade_k).",
    )
    return parser.parse_args()


def label_for(row: pd.Series) -> str:
    if int(row["k"]) == 0:
        return str(row["scenario"])
    return f"{row['scenario']} k={int(row['k'])}"


def plot_bar_eta08(df: pd.DataFrame, outdir: Path) -> list[Path]:
    subset = df[(df["eta"] == 0.8) & (df["k"] == 0) & (df["scenario"].isin(["BK", "DQT", "EQT"]))]
    upgrades = df[(df["eta"] == 0.8) & (df["scenario"] == "EQT_UPGRADE") & (df["k"] > 0)]
    rows = []
    if not subset.empty:
        rows.extend(subset.to_dict("records"))
    if not upgrades.empty:
        best = upgrades.loc[upgrades["mean_success_rate"].idxmax()].to_dict()
        rows.append(best)

    if not rows:
        return []

    labels = [label_for(pd.Series(row)) for row in rows]
    means = [row["mean_success_rate"] for row in rows]
    yerr = [
        [row["mean_success_rate"] - row["ci95_low"], row["ci95_high"] - row["mean_success_rate"]]
        for row in rows
    ]

    plt.figure(figsize=(7, 4))
    plt.bar(labels, means, color="#4c78a8", yerr=list(zip(*yerr)), capsize=4)
    plt.ylabel("Availability (success rate)")
    plt.title("Availability at eta=0.8")
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()

    png = outdir / "availability_bar_eta08.png"
    pdf = outdir / "availability_bar_eta08.pdf"
    plt.savefig(png, dpi=200)
    plt.savefig(pdf)
    plt.close()
    return [png, pdf]


def plot_eta_sweep(df: pd.DataFrame, outdir: Path) -> list[Path]:
    plt.figure(figsize=(7, 4))
    for (_, row_df) in df.groupby(["scenario", "k"]):
        row_df = row_df.sort_values("eta")
        label = label_for(row_df.iloc[0])
        x_vals = row_df["eta"].to_numpy()
        y_vals = row_df["mean_success_rate"].to_numpy()
        yerr_low = (row_df["mean_success_rate"] - row_df["ci95_low"]).to_numpy()
        yerr_high = (row_df["ci95_high"] - row_df["mean_success_rate"]).to_numpy()
        plt.errorbar(
            x_vals,
            y_vals,
            yerr=[yerr_low, yerr_high],
            marker="o",
            capsize=3,
            label=label,
        )
    plt.xlabel("eta")
    plt.ylabel("Availability (success rate)")
    plt.title("Availability vs eta")
    plt.legend(fontsize=8, ncol=2)
    plt.tight_layout()

    png = outdir / "availability_eta_sweep.png"
    pdf = outdir / "availability_eta_sweep.pdf"
    plt.savefig(png, dpi=200)
    plt.savefig(pdf)
    plt.close()
    return [png, pdf]


def plot_upgrade_k_sweep(df: pd.DataFrame, outdir: Path) -> list[Path]:
    subset = df[(df["scenario"] == "EQT_UPGRADE") & (df["eta"] == 0.8) & (df["k"] > 0)]
    if subset.empty:
        return []
    subset = subset.sort_values("k")
    plt.figure(figsize=(6, 4))
    x_vals = subset["k"].to_numpy()
    y_vals = subset["mean_success_rate"].to_numpy()
    yerr_low = (subset["mean_success_rate"] - subset["ci95_low"]).to_numpy()
    yerr_high = (subset["ci95_high"] - subset["mean_success_rate"]).to_numpy()
    plt.errorbar(
        x_vals,
        y_vals,
        yerr=[yerr_low, yerr_high],
        marker="o",
        capsize=3,
    )
    plt.xlabel("upgrade_k")
    plt.ylabel("Availability (success rate)")
    plt.title("Upgrade-k sweep at eta=0.8")
    plt.tight_layout()

    png = outdir / "upgrade_k_sweep_eta08.png"
    pdf = outdir / "upgrade_k_sweep_eta08.pdf"
    plt.savefig(png, dpi=200)
    plt.savefig(pdf)
    plt.close()
    return [png, pdf]


def main() -> int:
    args = parse_args()
    df = pd.read_csv(args.results)
    df["eta"] = df["eta"].astype(float)
    df["k"] = df["k"].astype(int)
    df["mean_success_rate"] = df["mean_success_rate"].astype(float)
    df["ci95_low"] = df["ci95_low"].astype(float)
    df["ci95_high"] = df["ci95_high"].astype(float)

    if args.study in set(df["study"]):
        df = df[df["study"] == args.study].copy()

    args.outdir.mkdir(parents=True, exist_ok=True)

    outputs = []
    outputs += plot_bar_eta08(df, args.outdir)
    outputs += plot_eta_sweep(df, args.outdir)
    outputs += plot_upgrade_k_sweep(df, args.outdir)

    for path in outputs:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
