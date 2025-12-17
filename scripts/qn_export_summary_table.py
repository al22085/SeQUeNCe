"""Export summary tables from phase and sensitivity outputs."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import List


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export summary tables from phase/sensitivity CSVs.")
    p.add_argument("--phase", type=Path, nargs="*", help="phase_crossover.csv paths")
    p.add_argument("--sensitivity", type=Path, nargs="*", help="crossover_sensitivity.csv paths")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_summary"))
    return p.parse_args()


def main():
    args = parse_args()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    summary_rows: List[List] = []
    if args.phase:
        for path in args.phase:
            if not path.exists():
                continue
            with path.open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    summary_rows.append(
                        [
                            path.name,
                            row.get("distance"),
                            row.get("eta_crossover"),
                            row.get("diff_at_crossover", ""),
                            "",
                            "",
                        ]
                    )
    if args.sensitivity:
        for path in args.sensitivity:
            if not path.exists():
                continue
            with path.open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    summary_rows.append(
                        [
                            path.name,
                            row.get("distance"),
                            row.get("eta_crossover"),
                            "",
                            row.get("knob"),
                            row.get("value"),
                        ]
                    )

    csv_path = out_dir / "summary_table.csv"
    headers = ["source", "distance", "eta_crossover", "diff_at_crossover", "knob", "value"]
    with csv_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(summary_rows)

    md_path = out_dir / "summary_table.md"
    with md_path.open("w") as f:
        f.write("| source | distance | eta_crossover | diff_at_crossover | knob | value |\n")
        f.write("|---|---|---|---|---|---|\n")
        for row in summary_rows:
            f.write("| " + " | ".join(row) + " |\n")

    print(f"Wrote {csv_path}")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
