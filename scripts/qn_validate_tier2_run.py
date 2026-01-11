"""Validate Tier2 run outputs and write a machine-readable report."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Dict, List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate Tier2 run completeness and strict preflight.")
    p.add_argument("--root-dir", type=Path, required=True)
    p.add_argument("--require-missing-zero", action="store_true", default=True)
    p.add_argument("--require-preflight-strict", action="store_true", default=True)
    return p.parse_args()


def load_csv(path: Path) -> List[Dict[str, str]]:
    with path.open() as f:
        return list(csv.DictReader(f))


def missing_pairs_from_pairs_csv(root: Path) -> Dict[str, int]:
    missing_total = 0
    missing_long = 0
    for topo_dir in root.iterdir():
        if not topo_dir.is_dir():
            continue
        pairs_csv = topo_dir / "pairs_repr3.csv"
        if not pairs_csv.exists():
            continue
        rows = load_csv(pairs_csv)
        for r in rows:
            if r.get("found", "").lower() in ("false", "0"):
                missing_total += 1
                if r.get("label", "").split("_")[0] == "long":
                    missing_long += 1
    return {"missing_total": missing_total, "missing_long": missing_long}


def main() -> None:
    args = parse_args()
    root = args.root_dir
    required = {
        "summary_upgrade_curves.csv": root / "summary_upgrade_curves.csv",
        "line_vs_curve_summary.csv": root / "line_vs_curve_summary.csv",
        "path_coverage_thresholds_summary.csv": root / "analysis_path_coverage" / "path_coverage_thresholds_summary.csv",
        "paper_key_findings.md": root / "plots_linearity" / "paper_key_findings.md",
        "parallel_report.json": root / "parallel_report.json",
    }
    missing_files = [name for name, path in required.items() if not path.exists()]
    if missing_files:
        raise SystemExit(f"Missing required files: {', '.join(missing_files)}")

    summary_rows = load_csv(required["summary_upgrade_curves.csv"])
    missing_counts = {}
    if summary_rows and "missing_pairs_total" in summary_rows[0]:
        missing_total = sum(int(r.get("missing_pairs_total", 0)) for r in summary_rows)
        missing_long = 0
        for r in summary_rows:
            by_label = r.get("missing_pairs_by_label", "")
            if "long" in by_label:
                try:
                    long_count = int(by_label.split("long:")[-1].split(",")[0])
                except Exception:
                    long_count = 0
                missing_long += long_count
        missing_counts = {"missing_total": missing_total, "missing_long": missing_long}
    else:
        missing_counts = missing_pairs_from_pairs_csv(root)

    if args.require_missing_zero and (missing_counts["missing_total"] > 0 or missing_counts["missing_long"] > 0):
        raise SystemExit(
            f"Missing pairs present: total={missing_counts['missing_total']} long={missing_counts['missing_long']}"
        )

    preflight = json.loads(required["parallel_report.json"].read_text())
    verify_info = preflight.get("verify_info", {})
    active_workers = verify_info.get("active_workers")
    requested_workers = preflight.get("requested_workers")
    aggregate_cpu = verify_info.get("aggregate_cpu")
    expected_cpu = verify_info.get("expected_cpu")
    if expected_cpu is None:
        expected_cpu = (preflight.get("effective_workers") or requested_workers or 0) * 100

    if args.require_preflight_strict:
        if active_workers != requested_workers:
            raise SystemExit(
                f"Strict preflight failed: active_workers={active_workers} requested_workers={requested_workers}"
            )
        if aggregate_cpu is None or aggregate_cpu < 0.95 * expected_cpu:
            raise SystemExit(
                f"Strict preflight failed: aggregate_cpu={aggregate_cpu} expected_cpu={expected_cpu}"
            )

    report = {
        "root_dir": str(root),
        "missing_pairs": missing_counts,
        "preflight": {
            "requested_workers": requested_workers,
            "active_workers": active_workers,
            "aggregate_cpu": aggregate_cpu,
            "expected_cpu": expected_cpu,
            "verify_mode": preflight.get("verify_mode"),
        },
        "required_files": {name: str(path) for name, path in required.items()},
        "status": "pass",
    }
    out_dir = root / "paper_artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "validation_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    print(f"Validation OK. Report: {report_path}")


if __name__ == "__main__":
    main()
