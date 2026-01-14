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


def plot_topology_bar_eta08(df: pd.DataFrame, outdir: Path) -> list[Path]:
    subset = df[(df["study"] == "study_topology_sweep") & (df["eta"] == 0.8)]
    if subset.empty:
        return []

    topologies = sorted(subset["topology"].unique())
    scenarios = [("BK", 0), ("EQT", 0), ("EQT_UPGRADE", None)]
    data = {scenario: [] for scenario, _ in scenarios}
    errs = {scenario: [] for scenario, _ in scenarios}

    for topo in topologies:
        topo_rows = subset[subset["topology"] == topo]
        for scenario, k in scenarios:
            if scenario == "EQT_UPGRADE":
                rows = topo_rows[(topo_rows["scenario"] == scenario) & (topo_rows["k"] > 0)]
                if rows.empty:
                    data[scenario].append(0.0)
                    errs[scenario].append((0.0, 0.0))
                    continue
                row = rows.loc[rows["mean_success_rate"].idxmax()]
            else:
                rows = topo_rows[(topo_rows["scenario"] == scenario) & (topo_rows["k"] == k)]
                if rows.empty:
                    data[scenario].append(0.0)
                    errs[scenario].append((0.0, 0.0))
                    continue
                row = rows.iloc[0]
            mean = float(row["mean_success_rate"])
            data[scenario].append(mean)
            errs[scenario].append((mean - float(row["ci95_low"]), float(row["ci95_high"]) - mean))

    width = 0.25
    x_vals = list(range(len(topologies)))
    plt.figure(figsize=(max(7, len(topologies) * 1.2), 4))
    colors = {"BK": "#4c78a8", "EQT": "#72b7b2", "EQT_UPGRADE": "#f58518"}
    for i, (scenario, _) in enumerate(scenarios):
        offsets = [x + (i - 1) * width for x in x_vals]
        yerr = list(zip(*errs[scenario])) if errs[scenario] else None
        plt.bar(
            offsets,
            data[scenario],
            width=width,
            color=colors.get(scenario, "#4c78a8"),
            yerr=yerr,
            capsize=3,
            label=scenario,
        )
    plt.xticks(x_vals, topologies, rotation=30, ha="right")
    plt.ylabel("Availability (success rate)")
    plt.title("Availability at eta=0.8 across topologies")
    plt.legend(fontsize=8, ncol=3)
    plt.tight_layout()

    png = outdir / "topology_bar_eta08.png"
    pdf = outdir / "topology_bar_eta08.pdf"
    plt.savefig(png, dpi=200)
    plt.savefig(pdf)
    plt.close()
    return [png, pdf]


def main() -> int:
    args = parse_args()
    df_all = pd.read_csv(args.results)
    df_all["eta"] = df_all["eta"].astype(float)
    df_all["k"] = df_all["k"].astype(int)
    df_all["mean_success_rate"] = df_all["mean_success_rate"].astype(float)
    df_all["ci95_low"] = df_all["ci95_low"].astype(float)
    df_all["ci95_high"] = df_all["ci95_high"].astype(float)
    if "topology" not in df_all.columns:
        df_all["topology"] = "nsfnet"

    df = df_all
    if args.study in set(df_all["study"]):
        df = df_all[df_all["study"] == args.study].copy()

    args.outdir.mkdir(parents=True, exist_ok=True)

    outputs = []
    outputs += plot_bar_eta08(df, args.outdir)
    outputs += plot_eta_sweep(df, args.outdir)
    outputs += plot_upgrade_k_sweep(df, args.outdir)
    outputs += plot_topology_bar_eta08(df_all, args.outdir)

    for path in outputs:
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
