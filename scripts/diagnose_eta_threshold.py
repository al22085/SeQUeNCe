#!/usr/bin/env python3
"""Compute served/deadline diagnostics for eta-threshold runs."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose eta-threshold raw logs.")
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=Path("out/paper_artifacts/eta_threshold/raw"),
        help="Root directory containing entanglement_service_raw.csv files.",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("out/paper_artifacts/eta_threshold/diagnostics"),
        help="Output directory for diagnostics artifacts.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("scripts/eta_threshold_config.json"),
        help="Config JSON for eta list (optional).",
    )
    return parser.parse_args()


def load_eta_list(config_path: Path) -> list[float] | None:
    if not config_path.exists():
        return None
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        etas = data.get("etas")
        if not etas:
            return None
        return sorted(float(val) for val in etas)
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return None


def find_raw_files(raw_root: Path) -> list[Path]:
    if raw_root.exists():
        files = sorted(raw_root.rglob("entanglement_service_raw.csv"))
        if files:
            print(f"Search root: {raw_root}")
            print(f"Found {len(files)} raw files under {raw_root}")
            return files

    fallback_root = Path("out")
    files = sorted(fallback_root.rglob("entanglement_service_raw.csv"))
    print(f"Search root: {raw_root} (no files found, fallback to {fallback_root})")
    print(f"Found {len(files)} raw files under {fallback_root}")
    return files


def parse_scenario_eta(path: Path) -> tuple[str, float]:
    parts = path.parts
    for idx, part in enumerate(parts):
        if not part.startswith("eta_"):
            continue
        try:
            eta = float(part.split("eta_")[-1])
        except ValueError:
            continue
        if idx == 0:
            raise ValueError(f"Could not parse scenario from {path}")
        scenario = parts[idx - 1]
        return scenario, eta
    raise ValueError(f"Could not parse eta from {path}")


def to_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(int) != 0
    lowered = series.astype(str).str.strip().str.lower()
    return lowered.isin(["true", "1", "t", "yes", "y"])


def accumulate_stats(files: Iterable[Path]) -> dict[tuple[str, float], dict[str, float]]:
    stats: dict[tuple[str, float], dict[str, float]] = defaultdict(
        lambda: {
            "n_total": 0,
            "n_served": 0,
            "n_miss": 0,
            "n_success": 0,
            "slack_sum": 0.0,
            "t_done_sum": 0.0,
        }
    )

    for path in files:
        scenario, eta = parse_scenario_eta(path)
        df = pd.read_csv(path)
        n_total = int(len(df))
        served = to_bool(df["served"])
        deadline = pd.to_numeric(df["deadline_s"], errors="coerce")
        t_done = pd.to_numeric(df["t_done_s"], errors="coerce")
        served_count = int(served.sum())
        miss_mask = served & (t_done > deadline)
        miss_count = int(miss_mask.sum())
        success_mask = served & (t_done <= deadline)
        success_count = int(success_mask.sum())
        slack_sum = float((deadline[success_mask] - t_done[success_mask]).sum())
        t_done_sum = float(t_done[success_mask].sum())

        key = (scenario, eta)
        stats[key]["n_total"] += n_total
        stats[key]["n_served"] += served_count
        stats[key]["n_miss"] += miss_count
        stats[key]["n_success"] += success_count
        stats[key]["slack_sum"] += slack_sum
        stats[key]["t_done_sum"] += t_done_sum

    return stats


def build_rows(
    stats: dict[tuple[str, float], dict[str, float]],
    target_etas: list[float],
) -> list[dict[str, float]]:
    scenarios = sorted({scenario for scenario, _ in stats.keys()})
    scenario_order = ["BK", "EQT"]
    ordered = [s for s in scenario_order if s in scenarios] + [
        s for s in scenarios if s not in scenario_order
    ]

    rows: list[dict[str, float]] = []
    for scenario in ordered:
        available_etas = sorted(eta for (sc, eta) in stats if sc == scenario)
        base_eta = available_etas[0] if len(available_etas) == 1 else None
        if scenario == "BK" and base_eta is not None and len(target_etas) > 1:
            print(
                f"BK logs only found at eta={base_eta}; reusing for all target etas: {target_etas}"
            )

        for eta in target_etas:
            entry = stats.get((scenario, eta))
            if entry is None and scenario == "BK" and base_eta is not None:
                entry = stats.get((scenario, base_eta))
            if entry is None:
                rows.append(
                    {
                        "scenario": scenario,
                        "eta": eta,
                        "n_requests_total": 0,
                        "served_rate": float("nan"),
                        "miss_deadline_rate_given_served": float("nan"),
                        "mean_slack_for_success": float("nan"),
                        "mean_t_done_for_success": float("nan"),
                    }
                )
                continue

            n_total = entry["n_total"]
            n_served = entry["n_served"]
            n_miss = entry["n_miss"]
            n_success = entry["n_success"]
            slack_sum = entry["slack_sum"]
            t_done_sum = entry["t_done_sum"]

            served_rate = n_served / n_total if n_total else float("nan")
            miss_rate = n_miss / n_served if n_served else float("nan")
            mean_slack = slack_sum / n_success if n_success else float("nan")
            mean_t_done = t_done_sum / n_success if n_success else float("nan")

            rows.append(
                {
                    "scenario": scenario,
                    "eta": eta,
                    "n_requests_total": int(n_total),
                    "served_rate": served_rate,
                    "miss_deadline_rate_given_served": miss_rate,
                    "mean_slack_for_success": mean_slack,
                    "mean_t_done_for_success": mean_t_done,
                }
            )
    return rows


def write_macros(df: pd.DataFrame, outpath: Path) -> None:
    eta_low = 0.03
    eta_high = 0.30
    metrics = {
        "served_rate": "ServedRate",
        "miss_deadline_rate_given_served": "MissDeadlineGivenServed",
        "mean_slack_for_success": "MeanSlackForSuccess",
        "mean_t_done_for_success": "MeanTdoneForSuccess",
    }

    def pick_value(scenario: str, eta: float, col: str) -> float | None:
        row = df[(df["scenario"] == scenario) & (df["eta"] == eta)]
        if row.empty:
            return None
        return float(row[col].iloc[0])

    lines = ["% Auto-generated by scripts/diagnose_eta_threshold.py"]
    for scenario in sorted(df["scenario"].unique()):
        for eta, label in [(eta_low, "EtaLow"), (eta_high, "EtaHigh")]:
            for col, macro in metrics.items():
                value = pick_value(scenario, eta, col)
                if value is None:
                    continue
                lines.append(
                    f"\\def\\{macro}{label}{scenario}{{{value:.4f}}}".replace(
                        "{label}", label
                    )
                )
    outpath.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    files = find_raw_files(args.raw_root)
    if not files:
        raise SystemExit("No raw logs found; cannot compute diagnostics.")

    etas = load_eta_list(args.config)
    if etas:
        print(f"Using eta list from config: {etas}")
    else:
        etas = sorted({parse_scenario_eta(path)[1] for path in files})
        print(f"Using eta list from raw logs: {etas}")

    stats = accumulate_stats(files)
    rows = build_rows(stats, etas)
    df = pd.DataFrame(rows)
    df = df.sort_values(["scenario", "eta"]).reset_index(drop=True)

    outdir = args.outdir
    outdir.mkdir(parents=True, exist_ok=True)
    csv_path = outdir / "eta_threshold_diagnosis.csv"
    df.to_csv(csv_path, index=False, float_format="%.6f")

    tex_path = outdir / "eta_threshold_diagnosis_auto.tex"
    write_macros(df, tex_path)

    print(f"Wrote {csv_path}")
    print(f"Wrote {tex_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
