#!/usr/bin/env python3
"""Generate summary figures for the paper artifacts.

Note: eta is passed into the strategy params (p_eg depends on eta), so eta is used.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plot summary figures for the paper.")
    parser.add_argument(
        "--results",
        type=Path,
        default=Path("out/paper_artifacts/results_agg.csv"),
        help="Path to results_agg.csv (falls back to results_master.csv if missing).",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("out/paper_artifacts/figures"),
        help="Output directory for figures.",
    )
    return parser.parse_args()


def pick_japanese_font() -> str | None:
    candidates = [
        "IPAexGothic",
        "IPAGothic",
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "TakaoGothic",
        "Yu Gothic",
        "MS Gothic",
        "Hiragino Sans",
        "Hiragino Kaku Gothic ProN",
    ]
    available = {font.name for font in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in available:
            return name
    return None


def configure_matplotlib(jp_font: str | None) -> None:
    font_family = [jp_font, "DejaVu Sans"] if jp_font else ["DejaVu Sans"]
    plt.rcParams.update(
        {
            "font.family": font_family,
            "font.size": 9,
            "axes.titlesize": 10,
            "axes.labelsize": 9,
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "axes.unicode_minus": False,
        }
    )


def draw_box(
    ax: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    text: str,
    *,
    text_kwargs: dict,
    facecolor: str = "#edf2f7",
    edgecolor: str = "#2f3e46",
) -> dict:
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=1.0,
        edgecolor=edgecolor,
        facecolor=facecolor,
    )
    ax.add_patch(box)
    ax.text(
        x + width / 2.0,
        y + height / 2.0,
        text,
        ha="center",
        va="center",
        **text_kwargs,
    )
    return {"x": x, "y": y, "w": width, "h": height}


def arrow_between(ax: plt.Axes, start: dict, end: dict) -> None:
    sx = start["x"] + start["w"] / 2.0
    sy = start["y"] + start["h"] / 2.0
    ex = end["x"] + end["w"] / 2.0
    ey = end["y"] + end["h"] / 2.0

    if abs(sy - ey) < 1e-6:
        if ex > sx:
            start_pt = (start["x"] + start["w"], sy)
            end_pt = (end["x"], ey)
        else:
            start_pt = (start["x"], sy)
            end_pt = (end["x"] + end["w"], ey)
    else:
        if ey > sy:
            start_pt = (sx, start["y"] + start["h"])
            end_pt = (ex, end["y"])
        else:
            start_pt = (sx, start["y"])
            end_pt = (ex, end["y"] + end["h"])

    ax.annotate(
        "",
        xy=end_pt,
        xytext=start_pt,
        arrowprops=dict(arrowstyle="-|>", color="#2f3e46", linewidth=1.0, mutation_scale=12),
    )


def plot_method_diagram(outdir: Path, jp_font: str | None) -> list[Path]:
    fig, ax = plt.subplots(figsize=(4.0, 4.0))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    text_kwargs = {"fontsize": 8}
    if jp_font:
        text_kwargs["fontfamily"] = jp_font

    width = 0.28
    height = 0.18
    top_y = 0.62
    bottom_y = 0.18
    x_positions = [0.04, 0.36, 0.68]

    labels = [
        "QKDサービス要求\n（締切）",
        "SeQUeNCe\nシミュレーション\n(BK vs EQT\n+ トランスデューサ\n+ テレポーテーション)",
        "要求ごとの生ログ",
        "requests.csvへ\n正規化",
        "可用性を計算",
        "集計 + プロット",
    ]

    boxes = []
    boxes.append(draw_box(ax, x_positions[0], top_y, width, height, labels[0], text_kwargs=text_kwargs))
    boxes.append(draw_box(ax, x_positions[1], top_y, width, height, labels[1], text_kwargs=text_kwargs))
    boxes.append(draw_box(ax, x_positions[2], top_y, width, height, labels[2], text_kwargs=text_kwargs))
    boxes.append(
        draw_box(ax, x_positions[2], bottom_y, width, height, labels[3], text_kwargs=text_kwargs)
    )
    boxes.append(
        draw_box(ax, x_positions[1], bottom_y, width, height, labels[4], text_kwargs=text_kwargs)
    )
    boxes.append(
        draw_box(ax, x_positions[0], bottom_y, width, height, labels[5], text_kwargs=text_kwargs)
    )

    for start, end in zip(boxes, boxes[1:]):
        arrow_between(ax, start, end)

    fig.subplots_adjust(left=0.03, right=0.97, top=0.97, bottom=0.03)
    png = outdir / "fig1_sequence_extension.png"
    pdf = outdir / "fig1_sequence_extension.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(pdf, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return [png, pdf]


def plot_main_result(df: pd.DataFrame, outdir: Path) -> list[Path]:
    subset = df[(df["study"] == "study_transducer_availability") & (df["eta"] == 0.8)]
    if "topology" in df.columns:
        subset = subset[subset["topology"] == "nsfnet"]
    subset = subset[subset["scenario"].isin(["BK", "EQT"])]

    scenario_order = ["BK", "EQT"]
    subset = subset.set_index("scenario").loc[scenario_order].reset_index()

    if subset.empty or len(subset) != len(scenario_order):
        raise ValueError("Expected BK and EQT rows for eta=0.8 in study_transducer_availability.")

    labels = subset["scenario"].tolist()
    means = subset["mean_success_rate"].astype(float).tolist()
    yerr_low = (subset["mean_success_rate"] - subset["ci95_low"]).astype(float).tolist()
    yerr_high = (subset["ci95_high"] - subset["mean_success_rate"]).astype(float).tolist()

    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    colors = {"BK": "#4c78a8", "EQT": "#f58518"}
    ax.bar(
        labels,
        means,
        color=[colors[label] for label in labels],
        yerr=[yerr_low, yerr_high],
        capsize=4,
    )

    ymax = max(subset["ci95_high"].astype(float))
    if ymax <= 0:
        ymax = 0.05
    else:
        ymax = ymax * 1.15
    ax.set_ylim(0, ymax)
    ax.set_ylabel("Deadline success rate (availability)")
    title = "Availability (eta=0.8, nsfnet)" if "topology" in df.columns else "Availability (eta=0.8)"
    ax.set_title(title)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.6, color="#b0b0b0")
    fig.tight_layout()

    png = outdir / "fig2_main_result_eta08.png"
    pdf = outdir / "fig2_main_result_eta08.pdf"
    fig.savefig(png, dpi=300)
    fig.savefig(pdf)
    plt.close(fig)
    return [png, pdf]


def resolve_results_path(path: Path) -> Path:
    if path.exists():
        return path
    fallback = path.with_name("results_master.csv")
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Could not find results file at {path} or {fallback}.")


def main() -> None:
    args = parse_args()
    results_path = resolve_results_path(args.results)
    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    jp_font = pick_japanese_font()
    configure_matplotlib(jp_font)

    df = pd.read_csv(results_path)
    plot_method_diagram(outdir, jp_font)
    plot_main_result(df, outdir)


if __name__ == "__main__":
    main()
