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
        default=Path("out/paper_artifacts/eta_threshold/results_eta_threshold.csv"),
        help="Path to results_eta_threshold.csv.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("out/paper_artifacts/figures"),
        help="Output directory for figures.",
    )
    parser.add_argument(
        "--include-architecture-diagram",
        action="store_true",
        help="Render the Fig.1 architecture diagram.",
    )
    parser.add_argument(
        "--include-method-diagram",
        action="store_true",
        help="Render the legacy Fig.1 method diagram.",
    )
    return parser.parse_args()


def pick_japanese_font() -> str | None:
    candidates = [
        "Noto Sans CJK JP",
        "Noto Sans JP",
        "IPAexGothic",
        "IPAGothic",
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
            "font.size": 14,
            "axes.titlesize": 15,
            "axes.labelsize": 14,
            "xtick.labelsize": 13,
            "ytick.labelsize": 13,
            "legend.fontsize": 13,
            "axes.linewidth": 1.0,
            "lines.linewidth": 2.0,
            "lines.markersize": 7,
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
    facecolor: str = "#f8fafc",
    edgecolor: str = "#1f2937",
    linestyle: str | tuple = "solid",
    linewidth: float = 1.5,
) -> dict:
    box = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.02,rounding_size=0.02",
        linewidth=linewidth,
        edgecolor=edgecolor,
        facecolor=facecolor,
        linestyle=linestyle,
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
        arrowprops=dict(arrowstyle="-|>", color="#1f2937", linewidth=1.5, mutation_scale=16),
    )


def plot_flow_diagram(outdir: Path, jp_font: str | None, stem: str) -> list[Path]:
    fig, ax = plt.subplots(figsize=(4.4, 3.4))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    text_kwargs = {"fontsize": 10}
    if jp_font:
        text_kwargs["fontfamily"] = jp_font

    labels_en = [
        "QKD requests\n(deadlines)",
        "SeQUeNCe sim\nBK vs EQT\n+ transducer\n+ teleport",
        "Per-request\nraw logs",
        "Normalize to\nrequests.csv",
        "Compute\navailability",
        "Aggregate\n+ plot",
    ]
    labels_jp = [
        "QKD要求\n（締切）",
        "SeQUeNCe\nシミュレーション\nBK vs EQT\n+ トランスデューサ\n+ テレポート",
        "要求ごとの\n生ログ",
        "requests.csvへ\n正規化",
        "可用性を\n計算",
        "集計\n+ プロット",
    ]
    labels = labels_jp if jp_font else labels_en

    steps = [
        {"label": labels[0], "is_added": True},
        {"label": labels[1], "is_added": True},
        {"label": labels[2], "is_added": False},
        {"label": labels[3], "is_added": True},
        {"label": labels[4], "is_added": True},
        {"label": labels[5], "is_added": True},
    ]

    width = 0.28
    height = 0.2
    top_y = 0.62
    bottom_y = 0.18
    x_positions = [0.05, 0.36, 0.67]
    line_added = "solid"
    line_existing = (0, (4, 2))

    boxes = []
    for idx, step in enumerate(steps[:3]):
        label = f"({idx + 1}) {step['label']}"
        linestyle = line_added if step["is_added"] else line_existing
        boxes.append(
            draw_box(
                ax,
                x_positions[idx],
                top_y,
                width,
                height,
                label,
                text_kwargs=text_kwargs,
                linestyle=linestyle,
            )
        )
    for idx, step in enumerate(steps[3:], start=3):
        label = f"({idx + 1}) {step['label']}"
        linestyle = line_added if step["is_added"] else line_existing
        boxes.append(
            draw_box(
                ax,
                x_positions[2 - (idx - 3)],
                bottom_y,
                width,
                height,
                label,
                text_kwargs=text_kwargs,
                linestyle=linestyle,
            )
        )

    for start, end in zip(boxes, boxes[1:]):
        arrow_between(ax, start, end)

    fig.tight_layout(pad=0.2)
    png = outdir / f"{stem}.png"
    pdf = outdir / f"{stem}.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(pdf, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return [png, pdf]


def draw_architecture_panel(ax: plt.Axes, jp_font: str | None) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    title = "（a）SeQUeNCe拡張アーキテクチャ"
    ax.text(0.02, 0.98, title, ha="left", va="top", fontsize=14, weight="bold")

    layer_x = 0.05
    layer_w = 0.9
    layer_h = 0.2
    layer_gap = 0.035
    title_x = layer_x + 0.02
    inner_x = layer_x + 0.2
    inner_w = 0.7
    module_h = 0.11

    layers = [
        {
            "title": "アプリ層（Application）",
            "modules": [("QKD要求生成", True)],
        },
        {
            "title": "制御・プロトコル層\n（Control/Protocol）",
            "modules": [
                ("戦略選択", True),
                ("テレポート\n経路", True),
                ("トランス\nデューサ", True),
            ],
        },
        {
            "title": "シミュレータ・コア\n（Simulator）",
            "modules": [
                ("イベント\nスケジューラ", False),
                ("エンタングルメント\n資源", False),
            ],
        },
        {
            "title": "出力・評価\n（Output/Eval）",
            "modules": [
                ("ログ出力", True),
                ("CSV正規化", True),
                ("可用性集計", True),
            ],
        },
    ]

    for idx, layer in enumerate(layers):
        y = 1.0 - (idx + 1) * layer_h - idx * layer_gap - 0.02
        bg = FancyBboxPatch(
            (layer_x, y),
            layer_w,
            layer_h,
            boxstyle="round,pad=0.01,rounding_size=0.02",
            linewidth=0.8,
            edgecolor="#9ca3af",
            facecolor="#f8fafc",
        )
        ax.add_patch(bg)
        ax.text(title_x, y + layer_h - 0.04, layer["title"], ha="left", va="top", fontsize=12)

        modules = layer["modules"]
        n = len(modules)
        gap = 0.02
        module_w = (inner_w - gap * (n - 1)) / n
        module_y = y + (layer_h - module_h) / 2.0
        for j, (label, is_added) in enumerate(modules):
            mx = inner_x + j * (module_w + gap)
            label_text = f"{label}\n（追加）" if is_added else label
            draw_box(
                ax,
                mx,
                module_y,
                module_w,
                module_h,
                label_text,
                text_kwargs={"fontsize": 14},
                facecolor="#ffffff",
                edgecolor="#111827",
                linestyle=(0, (4, 2)) if is_added else "solid",
            )

    legend_y = 0.02
    legend_items = [
        ("既存", "solid"),
        ("追加", (0, (4, 2))),
    ]
    legend_x = 0.05
    for idx, (label, linestyle) in enumerate(legend_items):
        lx = legend_x + idx * 0.22
        patch = FancyBboxPatch(
            (lx, legend_y),
            0.12,
            0.05,
            boxstyle="round,pad=0.01,rounding_size=0.01",
            linewidth=1.2,
            edgecolor="#111827",
            facecolor="#ffffff",
            linestyle=linestyle,
        )
        ax.add_patch(patch)
        ax.text(lx + 0.14, legend_y + 0.025, label, ha="left", va="center", fontsize=12)


def draw_workflow_panel(ax: plt.Axes, jp_font: str | None) -> None:
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    title = "（b）評価ワークフロー（データフロー）"
    ax.text(0.02, 0.98, title, ha="left", va="top", fontsize=14, weight="bold")

    labels_jp = [
        "パラメータ設定\n(トポロジ, η,\nシード, 要求数)",
        "qn_entanglement\n_service_availability.py\n実行",
        "要求ログCSV\n(arrival, deadline,\nserved, t_done)",
        "requests.csvへ\n正規化",
        "compute_availability.py\n→ seed別summary",
        "集計 → results_eta_threshold.csv\n+ Fig.2",
    ]
    labels_en = [
        "Parameter sweep\n(topology, eta,\nseeds, requests)",
        "Run qn_entanglement\n_service_availability.py",
        "Raw per-request CSV\n(arrival, deadline,\nserved, t_done)",
        "Normalize to\nrequests.csv",
        "compute_availability.py\n→ per-seed summary",
        "Aggregate → results_eta_threshold.csv\n+ Fig.2",
    ]
    labels = labels_jp if jp_font else labels_en

    steps = [{"label": labels[i], "is_added": True} for i in range(6)]
    width = 0.28
    height = 0.2
    top_y = 0.56
    bottom_y = 0.16
    x_positions = [0.05, 0.36, 0.67]
    boxes = []

    for idx, step in enumerate(steps[:3]):
        label = f"({idx + 1}) {step['label']}"
        boxes.append(
            draw_box(
                ax,
                x_positions[idx],
                top_y,
                width,
                height,
                label,
                text_kwargs={"fontsize": 14},
                facecolor="#ffffff",
                edgecolor="#111827",
                linestyle="solid",
            )
        )
    for idx, step in enumerate(steps[3:], start=3):
        label = f"({idx + 1}) {step['label']}"
        boxes.append(
            draw_box(
                ax,
                x_positions[2 - (idx - 3)],
                bottom_y,
                width,
                height,
                label,
                text_kwargs={"fontsize": 14},
                facecolor="#ffffff",
                edgecolor="#111827",
                linestyle="solid",
            )
        )

    for start, end in zip(boxes, boxes[1:]):
        arrow_between(ax, start, end)


def plot_architecture_diagram(outdir: Path, jp_font: str | None) -> list[Path]:
    fig = plt.figure(figsize=(4.6, 6.6))
    gs = fig.add_gridspec(2, 1, height_ratios=[1.1, 1.0], hspace=0.08)
    ax_top = fig.add_subplot(gs[0])
    ax_bottom = fig.add_subplot(gs[1])

    draw_architecture_panel(ax_top, jp_font)
    draw_workflow_panel(ax_bottom, jp_font)

    fig.tight_layout(pad=0.2)
    png = outdir / "fig1_sequence_architecture.png"
    pdf = outdir / "fig1_sequence_architecture.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(pdf, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return [png, pdf]


def plot_method_diagram(outdir: Path, jp_font: str | None) -> list[Path]:
    return plot_flow_diagram(outdir, jp_font, "fig1_sequence_extension")


def select_main_result_rows(df: pd.DataFrame, etas: list[float]) -> pd.DataFrame:
    subset = df[df["study"] == "study_transducer_availability"].copy()
    if "topology" in df.columns:
        subset = subset[subset["topology"].str.lower() == "nsfnet"]
    subset = subset[subset["scenario"].isin(["BK", "EQT"])]
    subset["eta"] = subset["eta"].round(2)
    subset = subset[subset["eta"].isin(etas)]

    scenario_order = ["BK", "EQT"]
    expected = {(scenario, eta) for scenario in scenario_order for eta in etas}
    present = set(zip(subset["scenario"], subset["eta"]))
    missing = expected - present
    if missing:
        missing_text = ", ".join(sorted(f"{scenario}@{eta}" for scenario, eta in missing))
        raise ValueError(f"Missing rows for main result eta sweep: {missing_text}.")
    if subset.duplicated(subset=["scenario", "eta"]).any():
        raise ValueError("Duplicate scenario/eta rows found for main result eta sweep.")

    subset["scenario"] = pd.Categorical(subset["scenario"], categories=scenario_order, ordered=True)
    subset = subset.sort_values(["scenario", "eta"]).reset_index(drop=True)
    return subset


def print_main_result_rows(subset: pd.DataFrame) -> None:
    table = subset[["scenario", "eta", "mean_success_rate", "ci95_low", "ci95_high"]].copy()
    print("Rows used for fig2_main_result_eta_sweep:")
    print(table.to_string(index=False, float_format=lambda x: f"{x:.4f}"))


def plot_main_result_eta_sweep(
    subset: pd.DataFrame, outdir: Path, etas: list[float], has_topology: bool
) -> list[Path]:
    fig, ax = plt.subplots(figsize=(4.2, 3.2))
    colors = {"BK": "#4c78a8", "EQT": "#f58518"}
    markers = {"BK": "o", "EQT": "s"}

    for scenario in ["BK", "EQT"]:
        rows = subset[subset["scenario"] == scenario].sort_values("eta")
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

    ymax = float(subset["ci95_high"].max())
    ymax = 0.05 if ymax <= 0 else ymax * 1.15
    ax.set_ylim(0, ymax)
    ax.set_xticks(etas)
    ax.set_xlabel("eta")
    ax.set_ylabel("Deadline success rate (availability)")
    title = "Availability vs eta (nsfnet)" if has_topology else "Availability vs eta"
    ax.set_title(title)
    ax.legend(frameon=False, fontsize=8)
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.6, color="#b0b0b0")
    fig.tight_layout()

    png = outdir / "fig2_main_result_eta_sweep.png"
    pdf = outdir / "fig2_main_result_eta_sweep.pdf"
    fig.savefig(png, dpi=300)
    fig.savefig(pdf)
    plt.close(fig)
    return [png, pdf]


def prepare_eta_threshold_rows(df: pd.DataFrame) -> pd.DataFrame:
    required = {"scenario", "eta", "mean_success_rate", "ci95_low", "ci95_high"}
    missing = required - set(df.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Missing columns in results: {missing_list}")
    subset = df[df["scenario"].isin(["BK", "EQT"])].copy()
    subset["eta"] = subset["eta"].astype(float)
    subset = subset.sort_values(["scenario", "eta"]).reset_index(drop=True)
    return subset


def compute_eta_thresholds(subset: pd.DataFrame) -> tuple[float | None, float | None]:
    bk = subset[subset["scenario"] == "BK"].set_index("eta")
    eqt = subset[subset["scenario"] == "EQT"].set_index("eta")
    eta_equal = None
    eta_sig = None
    for eta in sorted(subset["eta"].unique()):
        if eta not in bk.index or eta not in eqt.index:
            continue
        if eta_equal is None and eqt.loc[eta, "mean_success_rate"] >= bk.loc[eta, "mean_success_rate"]:
            eta_equal = eta
        if eta_sig is None and eqt.loc[eta, "ci95_low"] >= bk.loc[eta, "ci95_high"]:
            eta_sig = eta
    return eta_equal, eta_sig


def plot_eta_threshold(subset: pd.DataFrame, outdir: Path) -> list[Path]:
    fig, ax = plt.subplots(figsize=(4.2, 3.0))
    colors = {"BK": "#1f77b4", "EQT": "#d62728"}
    markers = {"BK": "o", "EQT": "s"}

    for scenario in ["BK", "EQT"]:
        rows = subset[subset["scenario"] == scenario].sort_values("eta")
        x_vals = rows["eta"].astype(float).tolist()
        y_mean = rows["mean_success_rate"].astype(float).tolist()
        y_low = rows["ci95_low"].astype(float).tolist()
        y_high = rows["ci95_high"].astype(float).tolist()
        ax.fill_between(
            x_vals,
            y_low,
            y_high,
            color=colors.get(scenario, "#1f77b4"),
            alpha=0.18,
            linewidth=0,
        )
        ax.plot(
            x_vals,
            y_mean,
            marker=markers.get(scenario, "o"),
            linestyle="-",
            linewidth=2.0,
            color=colors.get(scenario, "#1f77b4"),
            label=scenario,
        )

    eta_equal, eta_sig = compute_eta_thresholds(subset)
    if eta_equal is not None:
        ax.axvline(eta_equal, color="#111827", linestyle="--", linewidth=1.2)
        ax.text(
            eta_equal,
            0.98,
            "η_equal",
            rotation=90,
            va="top",
            ha="right",
            fontsize=12,
            transform=ax.get_xaxis_transform(),
        )
    if eta_sig is not None and (eta_equal is None or abs(eta_sig - eta_equal) > 1e-12):
        ax.axvline(eta_sig, color="#111827", linestyle=":", linewidth=1.2)
        ax.text(
            eta_sig,
            0.98,
            "η_sig",
            rotation=90,
            va="top",
            ha="right",
            fontsize=12,
            transform=ax.get_xaxis_transform(),
        )
    candidate_ticks = [0.01, 0.03, 0.05, 0.1, 0.15, 0.3, 0.5, 0.8]
    etas = sorted(subset["eta"].unique())
    measured_eta = 0.30
    if min(etas) <= measured_eta <= max(etas):
        ax.axvline(measured_eta, color="#6b7280", linestyle="-.", linewidth=1.2)
        ax.text(
            measured_eta,
            0.02,
            "実測例\n(≈0.30)",
            rotation=90,
            va="bottom",
            ha="right",
            fontsize=12,
            transform=ax.get_xaxis_transform(),
        )
    tick_vals = [
        val
        for val in candidate_ticks
        if min(etas) <= val <= max(etas) and any(abs(val - eta) < 1e-9 for eta in etas)
    ]
    if len(tick_vals) < 3:
        step = max(1, len(etas) // 6)
        tick_vals = etas[::step]
    tick_labels = {val: f"{val:g}" for val in tick_vals}

    ymax = float(subset["ci95_high"].max())
    if ymax <= 0:
        ymax = 0.05
    else:
        ymax = min(1.0, ymax * 1.4)

    ax.set_xscale("log")
    ax.set_xlim(min(tick_vals) * 0.9, max(tick_vals) * 1.1)
    ax.set_xticks(tick_vals)
    ax.set_xticklabels([tick_labels.get(val, f"{val:g}") for val in tick_vals])
    ax.set_ylim(0, ymax)
    ax.set_xlabel("Transducer efficiency η")
    ax.set_ylabel("Availability (deadline success rate)")
    ax.legend(frameon=False, ncol=2, loc="upper left")
    ax.set_axisbelow(True)
    ax.yaxis.grid(True, linestyle=":", linewidth=0.9, color="#b0b0b0")
    ax.xaxis.grid(True, linestyle=":", linewidth=0.6, color="#e5e7eb")

    fig.tight_layout(pad=0.2)

    png = outdir / "fig2_eta_threshold.png"
    pdf = outdir / "fig2_eta_threshold.pdf"
    fig.savefig(png, dpi=300, bbox_inches="tight", pad_inches=0.02)
    fig.savefig(pdf, bbox_inches="tight", pad_inches=0.02)
    plt.close(fig)
    return [png, pdf]


def resolve_results_path(path: Path) -> Path:
    if path.exists():
        return path
    raise FileNotFoundError(f"Could not find results file at {path}.")


def main() -> None:
    args = parse_args()
    results_path = resolve_results_path(args.results)
    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)

    jp_font = pick_japanese_font()
    configure_matplotlib(jp_font)

    df = pd.read_csv(results_path)
    subset = prepare_eta_threshold_rows(df)
    if args.include_architecture_diagram:
        plot_architecture_diagram(outdir, jp_font)
    if args.include_method_diagram:
        plot_method_diagram(outdir, jp_font)
    paths = plot_eta_threshold(subset, outdir)
    for path in paths:
        print(f"Wrote {path} (exists: {path.exists()})")


if __name__ == "__main__":
    main()
