#!/usr/bin/env python3
"""Compute availability as request success rate.

Example out/requests.csv:
request_id,src,dst,t_start,deadline,success,t_finish
r1,A,B,0.0,10.0,1,4.2
r2,A,C,1.0,12.0,0,
r3,B,C,2.0,8.0,1,6.5
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd

REQUIRED_COLUMNS = {"request_id", "src", "dst", "t_start", "deadline", "success", "t_finish"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compute request availability (success rate) from a requests CSV.",
    )
    parser.add_argument(
        "--requests",
        type=Path,
        default=Path("out/requests.csv"),
        help="Path to requests CSV (default: out/requests.csv).",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path("out"),
        help="Output directory for summary.csv (default: out).",
    )
    return parser


def load_requests(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Requests file not found: {path}")
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise ValueError(f"Failed to read CSV: {path} ({exc})") from exc
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        missing_list = ", ".join(sorted(missing))
        raise ValueError(f"Missing required columns: {missing_list}")
    return df


def validate_success_column(df: pd.DataFrame) -> pd.Series:
    success_raw = df["success"]
    success = pd.to_numeric(success_raw, errors="coerce")
    if success.isna().any():
        bad = success_raw[success.isna()].head(5).tolist()
        raise ValueError(
            "Invalid success values; expected 0/1. Examples: "
            + ", ".join(repr(v) for v in bad)
        )
    invalid = ~success.isin([0, 1])
    if invalid.any():
        bad = success[invalid].unique()[:5]
        raise ValueError(
            "Invalid success values; expected 0/1. Examples: "
            + ", ".join(repr(v) for v in bad)
        )
    return success.astype(int)


def compute_summary(df: pd.DataFrame) -> dict[str, object]:
    success = validate_success_column(df)
    n_requests = int(len(df))
    n_success = int(success.sum())
    request_success_rate = float(n_success / n_requests) if n_requests else 0.0

    if n_success == 0:
        mean_finish_time = None
    else:
        t_finish = pd.to_numeric(df.loc[success == 1, "t_finish"], errors="coerce")
        if t_finish.isna().any():
            count = int(t_finish.isna().sum())
            raise ValueError(
                f"t_finish missing or invalid for {count} successful requests."
            )
        mean_finish_time = float(t_finish.mean()) if not t_finish.empty else None

    return {
        "request_success_rate": request_success_rate,
        "n_requests": n_requests,
        "n_success": n_success,
        "mean_finish_time_for_success": mean_finish_time if mean_finish_time is not None else "",
    }


def write_summary(outdir: Path, summary: dict[str, object]) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "summary.csv"
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(summary.keys()))
        writer.writeheader()
        writer.writerow(summary)
    return out_path


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        df = load_requests(args.requests)
        summary = compute_summary(df)
        out_path = write_summary(args.outdir, summary)
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))

    print(f"request_success_rate: {summary['request_success_rate']:.6f}")
    print(f"n_requests: {summary['n_requests']}")
    print(f"n_success: {summary['n_success']}")
    print(f"summary_csv: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
