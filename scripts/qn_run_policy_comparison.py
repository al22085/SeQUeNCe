"""Run upgrade policy comparison on a single topology."""

from __future__ import annotations

import argparse
import csv
import subprocess
from pathlib import Path
from typing import List

import numpy as np


def parse_args():
    p = argparse.ArgumentParser(description="Compare upgrade policies for a single topology.")
    p.add_argument("--edge-distance-csv", type=Path, required=True)
    p.add_argument("--topology-id", type=str, required=True)
    p.add_argument("--pairs-csv", type=Path, required=True)
    p.add_argument("--upgrade-policies", type=str, default="global_rank,pair_demand,pair_path_only")
    p.add_argument("--upgrade-k-list", type=str, default="0,3,7,21")
    p.add_argument("--eta", type=float, default=0.9)
    p.add_argument("--target", type=float, default=0.99)
    p.add_argument("--kbits", type=float, default=1.0)
    p.add_argument("--seeds", type=str, default="0,1,2,3")
    p.add_argument("--segment-length-km", type=float, default=50.0)
    p.add_argument("--loss-db-per-km", type=float, default=0.2)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=5000)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=10000)
    p.add_argument("--coherence-opt-s", type=float, default=0.05)
    p.add_argument("--coherence-sc-s", type=float, default=0.1)
    p.add_argument("--horizon-s", type=float, default=0.3)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--load-min", type=float, default=0.001)
    p.add_argument("--load-max", type=float, default=5.0)
    p.add_argument("--load-tol", type=float, default=0.05)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--out-dir", type=Path, default=Path("out/policy_comparison"))
    return p.parse_args()


def parse_list(raw: str) -> List[str]:
    return [x for x in raw.split(",") if x]


def run_cmd(cmd: List[str]):
    subprocess.run(cmd, check=True)


def load_csv(path: Path):
    with path.open() as f:
        return list(csv.DictReader(f))


def compute_curvature(agg_rows, upgrade_ks):
    # compute slopes on EQT medians
    eqt = {int(r["upgrade_k"]): float(r["frontier_median"]) for r in agg_rows if r["strategy"] == "EQT"}
    f0 = eqt.get(upgrade_ks[0], 0.0)
    f3 = eqt.get(3, f0)
    f7 = eqt.get(7, f3)
    f21 = eqt.get(21, f7)
    s03 = (f3 - f0) / 3 if 3 in upgrade_ks else 0.0
    s37 = (f7 - f3) / 4 if 7 in upgrade_ks else 0.0
    s721 = (f21 - f7) / 14 if 21 in upgrade_ks else 0.0
    return s03, s37, s721, s37 - s03, s721 - s37


def main():
    args = parse_args()
    if args.workers < 2 or args.workers > 10:
        raise SystemExit("workers must be between 2 and 10")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    policies = parse_list(args.upgrade_policies)
    upgrade_ks = [int(x) for x in parse_list(args.upgrade_k_list)]

    rows = []
    for policy in policies:
        out_dir = args.out_dir / f"{args.topology_id}_{policy}"
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "python",
            "scripts/qn_entanglement_service_robustness_frontier.py",
            "--pairs-csv",
            str(args.pairs_csv),
            "--etas",
            str(args.eta),
            "--strategies",
            "BK,EQT",
            "--upgrade-k-list",
            args.upgrade_k_list,
            "--targets",
            str(args.target),
            "--kbits-list",
            str(args.kbits),
            "--seeds",
            args.seeds,
            "--binary-search",
            "--load-min",
            str(args.load_min),
            "--load-max",
            str(args.load_max),
            "--load-tol",
            str(args.load_tol),
            "--horizon-s",
            str(args.horizon_s),
            "--tau-s",
            str(args.tau_s),
            "--attempt-rate-opt-hz",
            str(args.attempt_rate_opt_hz),
            "--attempt-rate-sc-hz",
            str(args.attempt_rate_sc_hz),
            "--coherence-opt-s",
            str(args.coherence_opt_s),
            "--coherence-sc-s",
            str(args.coherence_sc_s),
            "--loss-db-per-km",
            str(args.loss_db_per_km),
            "--segment-length-km",
            str(args.segment_length_km),
            "--edge-distance-csv",
            str(args.edge_distance_csv),
            "--distance-dataset-id",
            args.topology_id,
            "--network-scope",
            "shortest_path",
            "--swap-schedule",
            "balanced",
            "--upgrade-policy",
            policy,
            "--topology-id",
            args.topology_id,
            "--workers",
            str(args.workers),
            "--out-dir",
            str(out_dir),
        ]
        run_cmd(cmd)

        agg_path = out_dir / "robust_frontier_agg.csv"
        agg_rows = load_csv(agg_path)
        bk0 = 0.0
        for r in agg_rows:
            if r["strategy"] == "BK" and int(r["upgrade_k"]) == 0:
                bk0 = float(r["frontier_median"])
                break
        s03, s37, s721, c1, c2 = compute_curvature(agg_rows, upgrade_ks)
        for r in agg_rows:
            ratio = float(r["frontier_median"]) / bk0 if bk0 > 0 else 0.0
            clipped = float(r["frontier_median"]) >= 0.95 * args.load_max
            rows.append(
                {
                    "topology_id": args.topology_id,
                    "policy": policy,
                    "upgrade_k": r["upgrade_k"],
                    "eta": r["eta"],
                    "target_A": r["target"],
                    "kbits": r["kbits"],
                    "frontier_median": r["frontier_median"],
                    "frontier_worst": r["frontier_min"],
                    "ratio_vs_BK0": ratio,
                    "s03": s03,
                    "s37": s37,
                    "s721": s721,
                    "c1": c1,
                    "c2": c2,
                    "clipped": clipped,
                }
            )

    out_csv = args.out_dir / "policy_comparison_agg.csv"
    with out_csv.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "topology_id",
                "policy",
                "upgrade_k",
                "eta",
                "target_A",
                "kbits",
                "frontier_median",
                "frontier_worst",
                "ratio_vs_BK0",
                "s03",
                "s37",
                "s721",
                "c1",
                "c2",
                "clipped",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {out_csv}")


if __name__ == "__main__":
    main()
