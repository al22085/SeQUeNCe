#!/usr/bin/env python3
"""Build consolidated results and LaTeX tables for paper artifacts."""

from __future__ import annotations

import argparse
import csv
import math
import subprocess
from pathlib import Path

import pandas as pd


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build paper artifact summaries from study outputs.")
    parser.add_argument("--out-root", type=Path, default=Path("out"), help="Root output directory.")
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("out/paper_artifacts"),
        help="Directory to write consolidated artifacts.",
    )
    return parser.parse_args()


def parse_served(raw: str | None) -> bool:
    if raw is None:
        return False
    text = str(raw).strip().lower()
    if text in ("1", "true", "t", "yes", "y"):
        return True
    if text in ("0", "false", "f", "no", "n", ""):
        return False
    try:
        return float(text) != 0.0
    except ValueError as exc:
        raise ValueError(f"Unrecognized served value: {raw}") from exc


def read_summary_csv(path: Path) -> tuple[float, int]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Empty summary CSV: {path}")
    row = rows[0]
    return float(row["request_success_rate"]), int(row["n_requests"])


def compute_success_from_raw(path: Path) -> tuple[float, int]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        required = {"arrival_s", "deadline_s", "served", "t_done_s"}
        missing = required - set(fieldnames)
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing raw columns in {path}: {missing_list}")
        n_requests = 0
        n_success = 0
        for row in reader:
            n_requests += 1
            served = parse_served(row.get("served"))
            deadline = float(row["deadline_s"])
            t_done_raw = row.get("t_done_s", "")
            t_done = float(t_done_raw) if str(t_done_raw).strip() not in ("", "None") else None
            success = served and t_done is not None and t_done <= deadline
            if success:
                n_success += 1
    success_rate = float(n_success / n_requests) if n_requests else 0.0
    return success_rate, n_requests


def parse_tag(tag: str, prefix: str) -> str:
    if not tag.startswith(prefix):
        raise ValueError(f"Expected tag prefix '{prefix}' in {tag}")
    return tag[len(prefix) :]


def collect_upgrade_k(derived_root: Path, rows: list[dict[str, object]]) -> None:
    for summary_path in derived_root.rglob("summary.csv"):
        rel = summary_path.relative_to(derived_root)
        if len(rel.parts) < 4:
            continue
        scenario = rel.parts[0]
        eta = float(parse_tag(rel.parts[1], "eta_"))
        k = int(parse_tag(rel.parts[2], "k_"))
        seed = int(parse_tag(rel.parts[3], "seed_"))
        success_rate, n_requests = read_summary_csv(summary_path)
        rows.append(
            {
                "study": "study_upgrade_k",
                "scenario": scenario,
                "eta": eta,
                "k": k,
                "seed": seed,
                "success_rate": success_rate,
                "n_requests": n_requests,
            }
        )


def collect_eta_sanity(derived_root: Path, rows: list[dict[str, object]]) -> None:
    for summary_path in derived_root.rglob("summary.csv"):
        rel = summary_path.relative_to(derived_root)
        if len(rel.parts) < 3:
            continue
        scenario = rel.parts[0]
        eta = float(parse_tag(rel.parts[1], "eta_"))
        seed = int(parse_tag(rel.parts[2], "seed_"))
        success_rate, n_requests = read_summary_csv(summary_path)
        rows.append(
            {
                "study": "study_eta_sanity",
                "scenario": scenario,
                "eta": eta,
                "k": 0,
                "seed": seed,
                "success_rate": success_rate,
                "n_requests": n_requests,
            }
        )


def collect_transducer(raw_root: Path, rows: list[dict[str, object]]) -> None:
    for raw_path in raw_root.rglob("entanglement_service_raw.csv"):
        rel = raw_path.relative_to(raw_root)
        if len(rel.parts) < 4:
            continue
        scenario = rel.parts[0]
        eta = float(parse_tag(rel.parts[1], "eta_"))
        seed = int(parse_tag(rel.parts[2], "seed_"))
        success_rate, n_requests = compute_success_from_raw(raw_path)
        rows.append(
            {
                "study": "study_transducer_availability",
                "scenario": scenario,
                "eta": eta,
                "k": 0,
                "seed": seed,
                "success_rate": success_rate,
                "n_requests": n_requests,
            }
        )


def latex_escape(text: str) -> str:
    return (
        text.replace("\\", "\\textbackslash ")
        .replace("_", "\\_")
        .replace("&", "\\&")
        .replace("%", "\\%")
    )


def format_float(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def git_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def write_table_full(agg: pd.DataFrame, path: Path) -> None:
    lines = [
        "% Auto-generated by scripts/build_paper_artifacts.py",
        "\\begin{tabular}{l l r r r r r}",
        "\\hline",
        "Study & Scenario & eta & k & n\\_seeds & mean & 95\\% CI \\\\",
        "\\hline",
    ]
    for _, row in agg.iterrows():
        ci = f"{format_float(row['ci95_low'])}--{format_float(row['ci95_high'])}"
        lines.append(
            " & ".join(
                [
                    latex_escape(str(row["study"])),
                    latex_escape(str(row["scenario"])),
                    format_float(float(row["eta"]), 2),
                    str(int(row["k"])),
                    str(int(row["n_seeds"])),
                    format_float(float(row["mean_success_rate"])),
                    ci,
                ]
            )
            + " \\\\"
        )
    lines.extend(["\\hline", "\\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def write_table_compact(agg: pd.DataFrame, path: Path) -> dict[str, float]:
    subset = agg[(agg["study"] == "study_upgrade_k") & (agg["eta"] == 0.8)]
    rows = []
    key_vals: dict[str, float] = {}
    for scenario in ("BK", "DQT", "EQT"):
        row = subset[(subset["scenario"] == scenario) & (subset["k"] == 0)]
        if row.empty:
            continue
        rows.append((scenario, row.iloc[0]))
    upgrade_rows = subset[(subset["scenario"] == "EQT_UPGRADE") & (subset["k"] > 0)]
    best_upgrade = None
    if not upgrade_rows.empty:
        best_idx = upgrade_rows["mean_success_rate"].idxmax()
        best_upgrade = upgrade_rows.loc[best_idx]
        rows.append((f"EQT_UPGRADE k={int(best_upgrade['k'])}", best_upgrade))

    lines = [
        "% Auto-generated by scripts/build_paper_artifacts.py",
        "\\begin{tabular}{l r r}",
        "\\hline",
        "Scenario & mean & 95\\% CI \\\\",
        "\\hline",
    ]
    for label, row in rows:
        ci = f"{format_float(row['ci95_low'])}--{format_float(row['ci95_high'])}"
        lines.append(
            " & ".join([latex_escape(label), format_float(row["mean_success_rate"]), ci]) + " \\\\"
        )
    lines.extend(["\\hline", "\\end{tabular}", ""])
    path.write_text("\n".join(lines), encoding="utf-8")

    for scenario, row in rows:
        if scenario.startswith("EQT_UPGRADE"):
            key_vals["BestUpgradeAvail"] = float(row["mean_success_rate"])
            key_vals["BestUpgradeK"] = float(row["k"])
        else:
            key_vals[f"{scenario}Avail"] = float(row["mean_success_rate"])
    return key_vals


def write_macros(path: Path, values: dict[str, float]) -> None:
    lines = ["% Auto-generated by scripts/build_paper_artifacts.py"]
    if "BKAvail" in values:
        lines.append(f"\\newcommand{{\\BKAvail}}{{{format_float(values['BKAvail'])}}}")
    if "DQTAvail" in values:
        lines.append(f"\\newcommand{{\\DQTAvail}}{{{format_float(values['DQTAvail'])}}}")
    if "EQTAvail" in values:
        lines.append(f"\\newcommand{{\\EQTAvail}}{{{format_float(values['EQTAvail'])}}}")
    if "BestUpgradeAvail" in values:
        lines.append(
            f"\\newcommand{{\\BestUpgradeAvail}}{{{format_float(values['BestUpgradeAvail'])}}}"
        )
    if "BestUpgradeK" in values:
        lines.append(f"\\newcommand{{\\BestUpgradeK}}{{{int(values['BestUpgradeK'])}}}")
    if "BKAvail" in values and "BestUpgradeAvail" in values:
        gain = values["BestUpgradeAvail"] - values["BKAvail"]
        lines.append(f"\\newcommand{{\\AvailGain}}{{{format_float(gain)}}}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_readme(path: Path, agg: pd.DataFrame, out_root: Path) -> None:
    key_findings = []
    subset = agg[(agg["study"] == "study_upgrade_k") & (agg["eta"] == 0.8)]
    if not subset.empty:
        bk = subset[(subset["scenario"] == "BK") & (subset["k"] == 0)]
        if not bk.empty:
            key_findings.append(
                f"eta=0.8 BK mean={format_float(float(bk.iloc[0]['mean_success_rate']))} "
                f"(95% CI {format_float(float(bk.iloc[0]['ci95_low']))}--"
                f"{format_float(float(bk.iloc[0]['ci95_high']))})."
            )
        upgrades = subset[(subset["scenario"] == "EQT_UPGRADE") & (subset["k"] > 0)]
        if not upgrades.empty:
            best = upgrades.loc[upgrades["mean_success_rate"].idxmax()]
            key_findings.append(
                f"eta=0.8 best EQT_UPGRADE k={int(best['k'])} mean="
                f"{format_float(float(best['mean_success_rate']))} "
                f"(95% CI {format_float(float(best['ci95_low']))}--"
                f"{format_float(float(best['ci95_high']))})."
            )

    raw_notes = []
    upgrade_tar = out_root / "study_upgrade_k_raw.tar.gz"
    upgrade_raw = out_root / "study_upgrade_k" / "raw"
    if upgrade_tar.exists():
        raw_notes.append(f"- upgrade-k raw archive: {upgrade_tar}")
    elif upgrade_raw.exists():
        raw_notes.append(f"- upgrade-k raw CSVs: {upgrade_raw}")

    transducer_raw = out_root / "study_transducer_availability" / "raw"
    if transducer_raw.exists():
        raw_notes.append(f"- transducer availability raw CSVs: {transducer_raw}")
    eta_sanity_raw = out_root / "study_eta_sanity" / "raw"
    if eta_sanity_raw.exists():
        raw_notes.append(f"- eta sanity raw CSVs: {eta_sanity_raw}")

    lines = [
        "# Paper Artifacts",
        "",
        "Metric",
        "- Availability = deadline-based request success rate.",
        "- success = (served == 1) AND (t_done_s <= deadline_s).",
        "",
        "Raw to requests.csv mapping",
        "- t_start = arrival_s",
        "- deadline = deadline_s",
        "- t_finish = t_done_s (success only)",
        "",
        "Eta usage",
        "- eta passed via --eta to scripts/qn_entanglement_service_availability.py.",
        "- eta used in sequence/qn/strategy_params.py (edge_params_for_strategy) to compute p_eg.",
        "",
        "Parameter matrix",
        "- study_transducer_availability: BK/DQT/EQT, eta=0.6/0.8/0.9, seeds=30, requests/seed=200, workers=20.",
        "- study_eta_sanity: DQT/EQT, eta=0.05/0.95, seeds=10, requests/seed=200, workers=20.",
        "- study_upgrade_k: BK/DQT/EQT (k=0) + EQT_UPGRADE (k=1,2,4,8), eta=0.6/0.8/0.9, seeds=30, requests/seed=200, workers=20.",
        "",
        "Commands",
        "- Batch runner: scripts/run_upgrade_k_batch.py (eta=0.6/0.8/0.9, seeds 0-30, workers=20).",
        "- Availability: scripts/compute_availability.py.",
        "- Consolidation: scripts/build_paper_artifacts.py.",
        "- Plots: scripts/plot_paper_artifacts.py.",
    ]
    lines.append("")
    lines.append("Raw data")
    if raw_notes:
        lines.extend(raw_notes)
    else:
        lines.append("- (raw data not found in out/)")
    lines.extend(
        [
            "",
            f"Git commit: {git_hash()}",
            "",
            "Key findings",
        ]
    )
    if key_findings:
        for item in key_findings:
            lines.append(f"- {item}")
    else:
        lines.append("- (no findings available; results_agg.csv has no eta=0.8 rows).")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    out_root = args.out_root
    artifacts_dir = args.artifacts_dir
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []

    upgrade_k_dir = out_root / "study_upgrade_k" / "derived"
    eta_sanity_dir = out_root / "study_eta_sanity" / "derived"
    transducer_raw_dir = out_root / "study_transducer_availability" / "raw"

    if upgrade_k_dir.exists():
        collect_upgrade_k(upgrade_k_dir, rows)
    if eta_sanity_dir.exists():
        collect_eta_sanity(eta_sanity_dir, rows)
    if transducer_raw_dir.exists():
        collect_transducer(transducer_raw_dir, rows)

    if not rows:
        raise SystemExit("No study results found to aggregate.")

    df = pd.DataFrame(rows)
    df["eta"] = df["eta"].astype(float)
    df["k"] = df["k"].astype(int)
    df["seed"] = df["seed"].astype(int)
    df["success_rate"] = df["success_rate"].astype(float)

    df_master = df[["study", "scenario", "eta", "k", "seed", "success_rate"]].sort_values(
        ["study", "scenario", "eta", "k", "seed"]
    )
    df_master.to_csv(artifacts_dir / "results_master.csv", index=False)

    agg = (
        df.groupby(["study", "scenario", "eta", "k"], as_index=False)
        .agg(
            n_seeds=("seed", "count"),
            n_requests_total=("n_requests", "sum"),
            mean_success_rate=("success_rate", "mean"),
            std_success_rate=("success_rate", "std"),
        )
        .sort_values(["study", "scenario", "eta", "k"])
    )
    agg["std_success_rate"] = agg["std_success_rate"].fillna(0.0)
    agg["ci95_low"] = agg["mean_success_rate"] - 1.96 * agg["std_success_rate"] / agg["n_seeds"].pow(0.5)
    agg["ci95_high"] = agg["mean_success_rate"] + 1.96 * agg["std_success_rate"] / agg["n_seeds"].pow(0.5)
    agg.to_csv(artifacts_dir / "results_agg.csv", index=False)

    write_table_full(agg, artifacts_dir / "results_table_full.tex")
    key_vals = write_table_compact(agg, artifacts_dir / "results_table_compact.tex")
    write_macros(artifacts_dir / "results_auto.tex", key_vals)
    write_readme(artifacts_dir / "README.md", agg, out_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
