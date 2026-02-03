#!/usr/bin/env python3
"""Plot thesis artifact v3 figures without re-running simulations."""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot thesis artifact v3 figures.")
    parser.add_argument(
        "--topology-results",
        type=Path,
        default=Path("out/thesis_artifacts_v3/results/results_topology_normalized.csv"),
        help="Path to results_topology_normalized.csv.",
    )
    parser.add_argument(
        "--upgrade-k-usage",
        type=Path,
        default=Path("out/thesis_artifacts_v3/diagnostics/upgrade_k_usage.csv"),
        help="Path to upgrade_k_usage.csv.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("out/thesis_artifacts_v3/figures"),
        help="Output directory for figures.",
    )
    parser.add_argument("--dpi", type=int, default=300, help="PNG DPI.")
    parser.add_argument("--pad", type=float, default=0.08, help="Padding for tight bounding box.")
    return parser.parse_args()


def configure_matplotlib() -> None:
    plt.rcParams.update(
        {
            "font.size": 13,
            "axes.labelsize": 14,
            "axes.titlesize": 14,
            "xtick.labelsize": 12,
            "ytick.labelsize": 12,
            "legend.fontsize": 12,
            "lines.linewidth": 2.2,
            "lines.markersize": 9,
            "axes.linewidth": 1.2,
            "axes.unicode_minus": False,
        }
    )


def plot_topology_normalized(df: pd.DataFrame, outdir: Path, dpi: int, pad: float) -> list[Path]:
    subset = df[df["scenario"].isin(["BK", "EQT"])].copy()
    if subset.empty:
        raise ValueError("No BK/EQT rows found in topology normalized results.")

    topologies = list(dict.fromkeys(subset["topology"].tolist()))
    if not topologies:
        raise ValueError("No topology labels found in results_topology_normalized.csv.")

    grouped = (
        subset.groupby(["topology", "scenario"], as_index=False)["mean_success_rate"]
        .mean()
        .reset_index(drop=True)
    )

    scenarios = ["BK", "EQT"]
    values: dict[str, list[float]] = {scenario: [] for scenario in scenarios}
    for topo in topologies:
        for scenario in scenarios:
            row = grouped[(grouped["topology"] == topo) & (grouped["scenario"] == scenario)]
            val = float(row["mean_success_rate"].iloc[0]) if not row.empty else 0.0
            values[scenario].append(val)

    x_vals = np.arange(len(topologies), dtype=float)
    dx = 0.12
    colors = {"BK": "#4c78a8", "EQT": "#f58518"}
    markers = {"BK": "o", "EQT": "s"}
    zero_thresh = 5e-4

    fig, ax = plt.subplots(figsize=(max(6.2, len(topologies) * 1.35), 3.8))
    for scenario, offset in zip(scenarios, (-dx, dx)):
        xs = x_vals + offset
        ys = values[scenario]
        ax.errorbar(
            xs,
            ys,
            yerr=np.zeros(len(ys)),
            fmt=markers.get(scenario, "o"),
            linestyle="none",
            markersize=9,
            color=colors.get(scenario, "#4c78a8"),
            ecolor=colors.get(scenario, "#4c78a8"),
            elinewidth=2.0,
            capsize=4,
            label=scenario,
        )
        for xi, yi in zip(xs, ys):
            if abs(yi) <= zero_thresh:
                ax.annotate(
                    "0.000",
                    (xi, yi),
                    textcoords="offset points",
                    xytext=(0, 6),
                    ha="center",
                    va="bottom",
                    fontsize=10,
                    color=colors.get(scenario, "#4c78a8"),
                )

    all_vals = [abs(v) for scenario_vals in values.values() for v in scenario_vals]
    max_abs = max(all_vals) if all_vals else 0.0
    y_span = max(0.01, max_abs * 1.2)
    ax.set_ylim(-y_span, y_span)
    ax.set_xlim(-0.5, len(topologies) - 0.5)
    ax.set_xticks(x_vals)
    ax.set_xticklabels(topologies, rotation=15, ha="right")
    ax.set_ylabel("Availability (success rate)")
    ax.axhline(0.0, color="#111827", linewidth=1.0)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.9, color="#d1d5db")
    ax.legend(frameon=False, ncol=2, loc="upper left")
    ax.text(
        0.5,
        0.9,
        "all methods = 0 under normalized conditions",
        transform=ax.transAxes,
        ha="center",
        va="top",
        fontsize=11,
        color="#4b5563",
        bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, boxstyle="round,pad=0.2"),
    )
    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / "fig_topology_normalized_bar.png"
    pdf = outdir / "fig_topology_normalized_bar.pdf"
    fig.savefig(png, dpi=dpi, bbox_inches="tight", pad_inches=pad)
    fig.savefig(pdf, bbox_inches="tight", pad_inches=pad)
    plt.close(fig)
    return [png, pdf]


def plot_upgrade_k_activation(df: pd.DataFrame, outdir: Path, dpi: int, pad: float) -> list[Path]:
    if df.empty:
        raise ValueError("Upgrade-k usage CSV is empty.")

    agg = (
        df.groupby("upgrade_k", as_index=False)[
            ["upgrade_activation_fraction", "path_upgraded_fraction"]
        ]
        .mean()
        .sort_values("upgrade_k")
        .reset_index(drop=True)
    )

    x_vals = agg["upgrade_k"].astype(float).to_numpy()
    activation = agg["upgrade_activation_fraction"].astype(float).to_numpy()
    path_frac = agg["path_upgraded_fraction"].astype(float).to_numpy()

    dx = 0.12
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    ax.plot(
        x_vals - dx,
        activation,
        marker="o",
        linewidth=2.2,
        markersize=9,
        color="#2563eb",
        label="Activation fraction",
    )
    ax.plot(
        x_vals + dx,
        path_frac,
        marker="s",
        linewidth=2.2,
        markersize=9,
        color="#f97316",
        label="Path upgraded fraction",
    )

    all_vals = np.concatenate([activation, path_frac]) if len(x_vals) else np.array([0.0])
    max_abs = float(np.max(np.abs(all_vals))) if all_vals.size else 0.0
    y_span = max(0.05, max_abs * 1.2)
    ax.set_ylim(-y_span, y_span)
    ax.set_xlim(min(x_vals) - 0.6, max(x_vals) + 0.6)
    ax.set_xticks(x_vals)
    ax.set_xlabel("upgrade_k")
    ax.set_ylabel("Fraction")
    ax.axhline(0.0, color="#111827", linewidth=1.0)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.9, color="#d1d5db")
    ax.legend(frameon=False, ncol=2, loc="upper left")

    if np.all(np.abs(all_vals) <= 1e-6):
        ax.text(
            0.5,
            0.9,
            "0 for all k",
            transform=ax.transAxes,
            ha="center",
            va="top",
            fontsize=11,
            color="#4b5563",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.8, boxstyle="round,pad=0.2"),
        )

    fig.tight_layout()

    outdir.mkdir(parents=True, exist_ok=True)
    png = outdir / "fig_upgrade_k_activation.png"
    pdf = outdir / "fig_upgrade_k_activation.pdf"
    fig.savefig(png, dpi=dpi, bbox_inches="tight", pad_inches=pad)
    fig.savefig(pdf, bbox_inches="tight", pad_inches=pad)
    plt.close(fig)
    return [png, pdf]


def main() -> int:
    args = parse_args()
    if not args.topology_results.exists():
        raise FileNotFoundError(f"Missing topology results CSV: {args.topology_results}")
    if not args.upgrade_k_usage.exists():
        raise FileNotFoundError(f"Missing upgrade-k usage CSV: {args.upgrade_k_usage}")

    configure_matplotlib()
    topology_df = pd.read_csv(args.topology_results)
    upgrade_df = pd.read_csv(args.upgrade_k_usage)

    outputs = []
    outputs += plot_topology_normalized(topology_df, args.outdir, args.dpi, args.pad)
    outputs += plot_upgrade_k_activation(upgrade_df, args.outdir, args.dpi, args.pad)

    for path in outputs:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
