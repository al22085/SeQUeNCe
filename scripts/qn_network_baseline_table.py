"""Generate markdown baseline table for network availability (SeQUeNCe)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Baseline table for qn_network_availability_sequence.")
    p.add_argument("--out", type=Path, default=None, help="Optional output file for the table.")
    return p.parse_args()


def run_case(strategy: str, arch: str, extra: list[str]) -> dict:
    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parents[0] / "qn_network_availability_sequence.py"),
        "--strategy",
        strategy,
        "--arch",
        arch,
        "--distance",
        "1e3",
        "--deadline-mode",
        "scaled",
        "--deadline-factor",
        "20",
        "--num-trials",
        "20",
        "--seed",
        "0",
        "--format",
        "json",
    ] + extra
    out = subprocess.check_output(cmd, text=True)
    import json

    return json.loads(out)


def main() -> None:
    args = parse_args()
    cases = []
    cases.append(run_case("BK", "optical", []))
    cases.append(run_case("EQT", "hybrid", ["--eta-source", "0.8", "--eta-dest", "0.8"]))
    cases.append(run_case("DQT", "hybrid", ["--dqt-eta-source", "0.8", "--dqt-eta-dest", "0.8"]))

    headers = ["arch", "strategy", "distance", "deadline_s", "trials", "satisfied", "availability_req", "mean_t_success"]
    lines = ["| " + " | ".join(headers) + " |", "|" + " --- |" * len(headers)]
    for c in cases:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(c.get("arch", "")),
                    str(c.get("strategy", "")),
                    f"{c.get('distance_per_link', '')}",
                    f"{c.get('deadline_s', ''):.6f}",
                    str(c.get("num_trials", "")),
                    str(c.get("satisfied", "")),
                    f"{c.get('availability_req', 0):.3f}",
                    "N/A" if c.get("mean_t_success") is None else f"{c.get('mean_t_success'):.2f}",
                ]
            )
            + " |"
        )
    table = "\n".join(lines)
    if args.out:
        args.out.write_text(table)
    print(table)


if __name__ == "__main__":
    main()
