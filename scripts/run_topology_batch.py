#!/usr/bin/env python3
"""Run topology sweep availability jobs in small batches and normalize outputs."""

from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
AVAILABILITY_SCRIPT = ROOT / "scripts" / "qn_entanglement_service_availability.py"
COMPUTE_AVAILABILITY = ROOT / "scripts" / "compute_availability.py"

BASE_SCENARIOS = [
    {"scenario": "BK", "strategy": "BK", "upgrade_k": 0},
    {"scenario": "EQT", "strategy": "EQT", "upgrade_k": 0},
]

REQUIRED_RAW_COLUMNS = {"src", "dst", "arrival_s", "deadline_s", "served", "t_done_s"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run topology sweep availability study in batches.")
    parser.add_argument("--topology", type=str, required=True, help="Topology id or path to distance CSV.")
    parser.add_argument("--eta", type=float, default=0.8, help="Transducer efficiency (default: 0.8).")
    parser.add_argument("--seed-start", type=int, required=True, help="Start seed (inclusive).")
    parser.add_argument("--seed-end", type=int, required=True, help="End seed (exclusive).")
    parser.add_argument("--workers", type=int, default=20, help="Parallel workers (max 20).")
    parser.add_argument("--requests-per-seed", type=int, default=200, help="Requests per seed.")
    parser.add_argument("--outdir", type=Path, default=Path("out/study_topology_sweep"), help="Study output dir.")
    parser.add_argument("--resume", action="store_true", help="Skip jobs with existing derived summaries.")
    return parser.parse_args()


def iter_seeds(start: int, end: int) -> Iterable[int]:
    if end <= start:
        raise ValueError("seed-end must be greater than seed-start")
    return range(start, end)


def format_eta(eta: float) -> str:
    return f"{eta:.1f}"


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


def resolve_topology_csv(raw: str) -> tuple[str, Path]:
    candidate = Path(raw)
    if candidate.is_file():
        return candidate.stem, candidate
    if candidate.suffix.lower() != ".csv":
        candidate = Path("data/topologybench_distances") / f"{raw}.csv"
    if candidate.is_file():
        return candidate.stem, candidate
    raise FileNotFoundError(f"Topology CSV not found for {raw}")


def best_upgrade_k(eta: float) -> int:
    results_path = ROOT / "out" / "paper_artifacts" / "results_agg.csv"
    if not results_path.exists():
        return 8
    try:
        import pandas as pd

        df = pd.read_csv(results_path)
        subset = df[
            (df["scenario"].astype(str).str.contains("UPGRADE", na=False))
            & (df["eta"].astype(float) == float(eta))
        ]
        if subset.empty:
            return 8
        best = subset.loc[subset["mean_success_rate"].astype(float).idxmax()]
        return int(best["k"])
    except Exception:
        return 8


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
    strategy: str,
    upgrade_k: int,
    eta: float,
    seed: int,
    workers: int,
    requests_per_seed: int,
    outdir: Path,
    topology_id: str,
    topology_csv: Path,
) -> Path:
    eta_label = format_eta(eta)
    raw_dir = outdir / "raw" / topology_id / scenario / f"eta_{eta_label}" / f"k_{upgrade_k}" / f"seed_{seed}"
    raw_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(AVAILABILITY_SCRIPT),
        "--topology",
        "nsfnet",
        "--edge-distance-csv",
        str(topology_csv),
        "--strategy",
        strategy,
        "--seed",
        str(seed),
        "--num-requests",
        str(requests_per_seed),
        "--eta",
        str(eta),
        "--workers",
        str(workers),
        "--upgrade-k",
        str(upgrade_k),
        "--upgrade-policy",
        "shortestpath_count",
        "--upgrade-mode",
        "edges",
        "--out-dir",
        str(raw_dir),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    raw_csv = raw_dir / "kbits_1.0" / "entanglement_service_raw.csv"
    if not raw_csv.exists():
        raise FileNotFoundError(f"Missing raw CSV after run: {raw_csv}")
    raw_copy = raw_dir / "raw.csv"
    shutil.copy2(raw_csv, raw_copy)
    return raw_csv


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


def main() -> int:
    args = parse_args()
    printed_header = [False]
    topology_id, topology_csv = resolve_topology_csv(args.topology)
    upgrade_k = best_upgrade_k(args.eta)
    scenarios = list(BASE_SCENARIOS)
    scenarios.append({"scenario": "EQT_UPGRADE", "strategy": "EQT", "upgrade_k": upgrade_k})

    jobs = []
    for seed in iter_seeds(args.seed_start, args.seed_end):
        for scenario in scenarios:
            jobs.append(
                {
                    "scenario": scenario["scenario"],
                    "strategy": scenario["strategy"],
                    "upgrade_k": scenario["upgrade_k"],
                    "seed": seed,
                }
            )

    attempted = 0
    skipped = 0
    succeeded = 0

    for job in jobs:
        eta_label = format_eta(args.eta)
        scenario = job["scenario"]
        upgrade_k = job["upgrade_k"]
        seed = job["seed"]
        derived_dir = (
            args.outdir
            / "derived"
            / topology_id
            / scenario
            / f"eta_{eta_label}"
            / f"k_{upgrade_k}"
            / f"seed_{seed}"
        )
        summary_csv = derived_dir / "summary.csv"
        if args.resume and summary_csv.exists():
            skipped += 1
            continue
        attempted += 1

        raw_dir = (
            args.outdir
            / "raw"
            / topology_id
            / scenario
            / f"eta_{eta_label}"
            / f"k_{upgrade_k}"
            / f"seed_{seed}"
        )
        raw_csv = raw_dir / "kbits_1.0" / "entanglement_service_raw.csv"
        if not raw_csv.exists():
            raw_csv = run_simulation(
                scenario=scenario,
                strategy=job["strategy"],
                upgrade_k=upgrade_k,
                eta=args.eta,
                seed=seed,
                workers=args.workers,
                requests_per_seed=args.requests_per_seed,
                outdir=args.outdir,
                topology_id=topology_id,
                topology_csv=topology_csv,
            )
        requests_csv = derived_dir / "requests.csv"
        normalize_raw(raw_csv, requests_csv, printed_header)
        summarize_requests(requests_csv, derived_dir)
        succeeded += 1

    total_summaries = len(list((args.outdir / "derived").rglob("summary.csv")))
    print(
        f"Attempted: {attempted} | Skipped: {skipped} | Succeeded: {succeeded} | summaries: {total_summaries}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
