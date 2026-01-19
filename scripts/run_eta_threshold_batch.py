#!/usr/bin/env python3
"""Run eta-threshold availability jobs in batches and aggregate results.

Note: eta is passed into strategy params (p_eg depends on eta).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AVAILABILITY_SCRIPT = ROOT / "scripts" / "qn_entanglement_service_availability.py"
COMPUTE_AVAILABILITY = ROOT / "scripts" / "compute_availability.py"

REQUIRED_RAW_COLUMNS = {"src", "dst", "arrival_s", "deadline_s", "served", "t_done_s"}
SCENARIO_ORDER = ["BK", "EQT"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run eta threshold availability study in batches.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("scripts/eta_threshold_config.json"),
        help="JSON config with eta sweep list.",
    )
    parser.add_argument("--eta", type=float, action="append", default=[], help="Eta value to run.")
    parser.add_argument("--etas", type=str, default="", help="Comma-separated eta list.")
    parser.add_argument("--scenarios", type=str, default="BK,EQT", help="Comma-separated scenarios.")
    parser.add_argument("--seed-start", type=int, default=0, help="Start seed (inclusive).")
    parser.add_argument("--seed-end", type=int, default=30, help="End seed (exclusive).")
    parser.add_argument("--workers", type=int, default=20, help="Parallel workers (max 20).")
    parser.add_argument("--requests-per-seed", type=int, default=200, help="Requests per seed.")
    parser.add_argument(
        "--outdir", type=Path, default=Path("out/study_eta_threshold"), help="Study output dir."
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("out/paper_artifacts"),
        help="Paper artifacts directory.",
    )
    parser.add_argument("--resume", action="store_true", help="Skip jobs with existing summaries.")
    parser.add_argument(
        "--aggregate-only", action="store_true", help="Only aggregate existing summaries."
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary run directories (for debugging).",
    )
    return parser.parse_args()


def iter_seeds(start: int, end: int) -> Iterable[int]:
    if end <= start:
        raise ValueError("seed-end must be greater than seed-start")
    return range(start, end)


def parse_list(raw: str) -> list[float]:
    if not raw:
        return []
    return [float(x) for x in raw.split(",") if x.strip()]


def load_etas(args: argparse.Namespace) -> list[float]:
    if args.eta:
        return sorted(set(args.eta))
    if args.etas:
        return sorted(set(parse_list(args.etas)))
    if not args.config.exists():
        raise FileNotFoundError(f"Config not found: {args.config}")
    payload = json.loads(args.config.read_text(encoding="utf-8"))
    etas = payload.get("etas", [])
    if not etas:
        raise ValueError("No etas found in config.")
    return [float(x) for x in etas]


def format_eta(eta: float) -> str:
    return f"{eta:.5f}"


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


def normalize_raw(raw_csv: Path, requests_csv: Path, printed_header: list[bool]) -> None:
    requests_csv.parent.mkdir(parents=True, exist_ok=True)
    with raw_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = REQUIRED_RAW_COLUMNS - set(fieldnames)
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing raw columns in {raw_csv}: {missing_list}")
        if not printed_header[0]:
            print(f"Raw columns: {fieldnames}")
            print("Mapping: src=src, dst=dst, t_start=arrival_s, deadline=deadline_s, t_finish=t_done_s")
            printed_header[0] = True

        rows = []
        for row in reader:
            src = row.get("src", "")
            dst = row.get("dst", "")
            t_start = float(row["arrival_s"])
            deadline = float(row["deadline_s"])
            served = parse_served(row.get("served"))
            t_done_raw = row.get("t_done_s", "")
            t_done = float(t_done_raw) if str(t_done_raw).strip() not in ("", "None") else None
            success = int(served and t_done is not None and t_done <= deadline)
            t_finish = "" if success == 0 else f"{t_done}"
            rows.append(
                {
                    "request_id": row.get("request_idx", ""),
                    "src": src,
                    "dst": dst,
                    "t_start": f"{t_start}",
                    "deadline": f"{deadline}",
                    "success": f"{success}",
                    "t_finish": t_finish,
                    "_sort": (t_start, src, dst),
                }
            )

    has_request_idx = any(r["request_id"] for r in rows)
    if not has_request_idx:
        rows.sort(key=lambda r: r["_sort"])
        for idx, row in enumerate(rows):
            row["request_id"] = str(idx)

    with requests_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["request_id", "src", "dst", "t_start", "deadline", "success", "t_finish"])
        for row in rows:
            writer.writerow(
                [
                    row["request_id"],
                    row["src"],
                    row["dst"],
                    row["t_start"],
                    row["deadline"],
                    row["success"],
                    row["t_finish"],
                ]
            )


def run_simulation(
    *,
    scenario: str,
    eta: float,
    seed: int,
    workers: int,
    requests_per_seed: int,
    temp_dir: Path,
) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(AVAILABILITY_SCRIPT),
        "--topology",
        "nsfnet",
        "--strategy",
        scenario,
        "--seed",
        str(seed),
        "--num-requests",
        str(requests_per_seed),
        "--eta",
        str(eta),
        "--workers",
        str(workers),
        "--out-dir",
        str(temp_dir),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def summarize_requests(requests_csv: Path, summary_dir: Path) -> None:
    cmd = [
        sys.executable,
        str(COMPUTE_AVAILABILITY),
        "--requests",
        str(requests_csv),
        "--outdir",
        str(summary_dir),
    ]
    subprocess.run(cmd, check=True)


def parse_tag(tag: str, prefix: str) -> str:
    if not tag.startswith(prefix):
        raise ValueError(f"Expected tag prefix '{prefix}' in {tag}")
    return tag[len(prefix) :]


def read_summary_csv(path: Path) -> tuple[float, int]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Empty summary CSV: {path}")
    row = rows[0]
    return float(row["request_success_rate"]), int(row["n_requests"])


def aggregate_results(derived_root: Path, outdir: Path, artifacts_dir: Path) -> Path | None:
    rows: list[dict[str, object]] = []
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
                "scenario": scenario,
                "eta": eta,
                "seed": seed,
                "success_rate": success_rate,
                "n_requests": n_requests,
            }
        )

    if not rows:
        print("No summaries found to aggregate.")
        return None

    df = pd.DataFrame(rows)
    df["eta"] = df["eta"].astype(float)
    df["seed"] = df["seed"].astype(int)
    df["success_rate"] = df["success_rate"].astype(float)

    agg = (
        df.groupby(["scenario", "eta"], as_index=False)
        .agg(
            n_seeds=("seed", "count"),
            n_requests_total=("n_requests", "sum"),
            mean_success_rate=("success_rate", "mean"),
            std_success_rate=("success_rate", "std"),
        )
        .sort_values(["scenario", "eta"])
    )
    agg["std_success_rate"] = agg["std_success_rate"].fillna(0.0)
    agg["ci95_low"] = agg["mean_success_rate"] - 1.96 * agg["std_success_rate"] / agg["n_seeds"].pow(0.5)
    agg["ci95_high"] = agg["mean_success_rate"] + 1.96 * agg["std_success_rate"] / agg["n_seeds"].pow(0.5)
    agg["ci95_low"] = agg["ci95_low"].clip(lower=0.0, upper=1.0)
    agg["ci95_high"] = agg["ci95_high"].clip(lower=0.0, upper=1.0)

    agg["scenario"] = pd.Categorical(agg["scenario"], categories=SCENARIO_ORDER, ordered=True)
    agg = agg.sort_values(["scenario", "eta"]).reset_index(drop=True)

    outdir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "results_eta_threshold.csv"
    artifacts_path = artifacts_dir / "results_eta_threshold.csv"
    agg.to_csv(out_path, index=False)
    agg.to_csv(artifacts_path, index=False)
    print(f"Wrote {out_path}")
    print(f"Wrote {artifacts_path}")
    return artifacts_path


def main() -> int:
    args = parse_args()
    etas = load_etas(args)
    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    derived_root = args.outdir / "derived"
    printed_header = [False]

    if not args.aggregate_only:
        attempted = 0
        skipped = 0
        succeeded = 0

        for eta in etas:
            eta_label = format_eta(eta)
            for scenario in scenarios:
                for seed in iter_seeds(args.seed_start, args.seed_end):
                    derived_dir = derived_root / scenario / f"eta_{eta_label}" / f"seed_{seed}"
                    summary_csv = derived_dir / "summary.csv"
                    if args.resume and summary_csv.exists():
                        skipped += 1
                        continue

                    raw_dir = args.outdir / "raw" / scenario / f"eta_{eta_label}"
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    raw_csv = raw_dir / f"seed_{seed}.csv"
                    raw_json = raw_dir / f"seed_{seed}.json"

                    if not raw_csv.exists():
                        temp_dir = args.outdir / "tmp" / scenario / f"eta_{eta_label}" / f"seed_{seed}"
                        run_simulation(
                            scenario=scenario,
                            eta=eta,
                            seed=seed,
                            workers=args.workers,
                            requests_per_seed=args.requests_per_seed,
                            temp_dir=temp_dir,
                        )
                        raw_source = temp_dir / "kbits_1.0" / "entanglement_service_raw.csv"
                        summary_source = temp_dir / "kbits_1.0" / "summary.json"
                        if not raw_source.exists():
                            raise FileNotFoundError(f"Missing raw CSV after run: {raw_source}")
                        shutil.copy2(raw_source, raw_csv)
                        if summary_source.exists():
                            shutil.copy2(summary_source, raw_json)
                        if not args.keep_temp and temp_dir.exists():
                            shutil.rmtree(temp_dir)

                    attempted += 1
                    requests_csv = derived_dir / "requests.csv"
                    normalize_raw(raw_csv, requests_csv, printed_header)
                    summarize_requests(requests_csv, derived_dir)
                    succeeded += 1

        total_summaries = len(list(derived_root.rglob("summary.csv")))
        print(
            f"Attempted: {attempted} | Skipped: {skipped} | Succeeded: {succeeded} | summaries: {total_summaries}"
        )

    aggregate_results(derived_root, args.outdir, args.artifacts_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
