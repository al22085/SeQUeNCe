#!/usr/bin/env python3
"""Plot BK vs EQT availability vs eta for the threshold study."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot eta-threshold availability curves.")
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("out/paper_artifacts/results_eta_threshold.csv"),
        help="Aggregated results CSV.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("out/paper_artifacts/figures"),
        help="Output directory for figures.",
    )
    return parser.parse_args()


def compute_threshold(df: pd.DataFrame) -> tuple[float | None, str]:
    etas = sorted(df["eta"].unique())
    for eta in etas:
        bk = df[(df["scenario"] == "BK") & (df["eta"] == eta)].iloc[0]
        eqt = df[(df["scenario"] == "EQT") & (df["eta"] == eta)].iloc[0]
        if eqt["mean_success_rate"] >= bk["mean_success_rate"]:
            if eqt["ci95_low"] >= bk["ci95_high"]:
                return float(eta), "non_overlap"
    for eta in etas:
        bk = df[(df["scenario"] == "BK") & (df["eta"] == eta)].iloc[0]
        eqt = df[(df["scenario"] == "EQT") & (df["eta"] == eta)].iloc[0]
        if eqt["mean_success_rate"] >= bk["mean_success_rate"]:
            return float(eta), "mean_only"
    return None, "none"


def main() -> int:
    args = parse_args()
    if not args.results.exists():
        raise FileNotFoundError(f"Missing results CSV: {args.results}")
    df = pd.read_csv(args.results)
    df = df[df["scenario"].isin(["BK", "EQT"])].copy()
    if df.empty:
        raise ValueError("No BK/EQT rows found in results.")

    etas = sorted(df["eta"].unique())
    threshold_eta, threshold_mode = compute_threshold(df)

    fig, ax = plt.subplots(figsize=(4.4, 3.2))
    colors = {"BK": "#4c78a8", "EQT": "#f58518"}
    markers = {"BK": "o", "EQT": "s"}

    for scenario in ["BK", "EQT"]:
        rows = df[df["scenario"] == scenario].sort_values("eta")
        x_vals = rows["eta"].astype(float).tolist()
        y_vals = rows["mean_success_rate"].astype(float).tolist()
        yerr_low = (rows["mean_success_rate"] - rows["ci95_low"]).astype(float).tolist()
        yerr_high = (rows["ci95_high"] - rows["mean_success_rate"]).astype(float).tolist()
        ax.errorbar(
            x_vals,
            y_vals,
            yerr=[yerr_low, yerr_high],
            marker=markers.get(scenario, "o"),
            linestyle="-",
            linewidth=1.2,
            capsize=3,
            color=colors.get(scenario, "#4c78a8"),
            label=scenario,
        )

    ymax = float(df["ci95_high"].max())
    ymax = 0.05 if ymax <= 0 else ymax * 1.2
    ax.set_ylim(0, ymax)
    ax.set_xscale("log")
    ax.set_xlim(min(etas) * 0.8, max(etas) * 1.2)
    ax.set_xticks(etas)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
    ax.set_xlabel("eta")
    ax.set_ylabel("Deadline success rate (availability)")
    ax.set_title("Availability vs eta (nsfnet)")
    ax.legend(frameon=False, fontsize=8)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.6, color="#b0b0b0")

    if threshold_eta is not None:
        ax.axvline(threshold_eta, color="#4a4a4a", linestyle="--", linewidth=1.0)
        label = "eta* (CI)" if threshold_mode == "non_overlap" else "eta* (mean)"
        ax.text(
            threshold_eta,
            ymax * 0.92,
            label,
            rotation=90,
            va="top",
            ha="right",
            fontsize=7,
            color="#4a4a4a",
        )
    else:
        ax.text(
            0.02,
            0.95,
            "No eta* (CI overlap)",
            transform=ax.transAxes,
            fontsize=7,
            va="top",
            ha="left",
            color="#4a4a4a",
        )

    fig.tight_layout()
    args.outdir.mkdir(parents=True, exist_ok=True)
    png = args.outdir / "fig2_eta_threshold.png"
    pdf = args.outdir / "fig2_eta_threshold.pdf"
    fig.savefig(png, dpi=300)
    fig.savefig(pdf)
    plt.close(fig)
    print(f"eta_star: {threshold_eta} (mode={threshold_mode})")
    print(f"Wrote {png}")
    print(f"Wrote {pdf}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
