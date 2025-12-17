"""2D phase sweep over distance x eta for hybrid strategies (BK/DQT/EQT)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_network_availability_sequence import run_trials


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def ci95(std: float, n: int) -> float:
    if n <= 0:
        return 0.0
    return 1.96 * std / math.sqrt(n)


def build_args(base, strategy: str, distance: float, eta: float, seed: int) -> SimpleNamespace:
    # hybrid arch; eta applies to DQT/EQT; BK ignores eta
    eta_source = base.eta_source
    eta_dest = base.eta_dest
    dqt_eta_source = base.dqt_eta_source
    dqt_eta_dest = base.dqt_eta_dest
    if strategy in ("EQT", "DQT"):
        eta_source = eta_dest = eta
        dqt_eta_source = dqt_eta_dest = eta
    return SimpleNamespace(
        strategy=strategy,
        arch="hybrid",
        distance=distance,
        deadline_mode=base.deadline_mode,
        deadline_ps=None,
        deadline_s=base.deadline_s,
        deadline_factor=base.deadline_factor,
        fiber_v=base.fiber_v,
        setup_factor=base.setup_factor,
        min_start_delay_s=base.min_start_delay_s,
        num_trials=base.num_trials,
        seed=seed,
        fidelity=base.fidelity,
        eta_source=eta_source,
        eta_dest=eta_dest,
        dqt_eta_source=dqt_eta_source,
        dqt_eta_dest=dqt_eta_dest,
        qt_eff=base.qt_eff,
        swap_success=1.0,
        mem_coh_s=base.mem_coh_s,
        attn=base.attn,
        cc_delay=base.cc_delay,
        sanity="off",
        format="json",
        out=None,
        debug=False,
    )


def write_csv(path: Path, headers: List[str], rows: Iterable[Tuple]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Distance x eta phase sweep (hybrid).")
    p.add_argument("--strategies", default="BK,DQT,EQT")
    p.add_argument("--distances", default="1000,2000")
    p.add_argument("--etas", default="0.6,0.8,1.0")
    p.add_argument("--seeds", default="0,1,2")
    p.add_argument("--num-trials", type=int, default=10)
    p.add_argument("--deadline-mode", choices=["absolute", "scaled"], default="scaled")
    p.add_argument("--deadline-s", type=float, default=0.1)
    p.add_argument("--deadline-factor", type=float, default=700.0)
    p.add_argument("--fiber-v", type=float, default=2e8)
    p.add_argument("--setup-factor", type=float, default=500.0)
    p.add_argument("--min-start-delay-s", type=float, default=0.01)
    p.add_argument("--eta-source", type=float, default=0.8)
    p.add_argument("--eta-dest", type=float, default=0.8)
    p.add_argument("--dqt-eta-source", type=float, default=0.8)
    p.add_argument("--dqt-eta-dest", type=float, default=0.8)
    p.add_argument("--optical-eta", type=float, default=1.0, help="Effective eta for optical components (for completeness; hybrid uses protocol etas).")
    p.add_argument("--qt-eff", type=float, default=None)
    p.add_argument("--mem-coh-s", type=float, default=0.005)
    p.add_argument("--attn", type=float, default=0.005)
    p.add_argument("--cc-delay", type=float, default=1e6)
    p.add_argument("--fidelity", type=float, default=0.5)
    p.add_argument("--workers", type=int, default=1, help="Parallel workers (capped at 4).")
    p.add_argument("--resume", action="store_true", help="Resume from existing raw CSV to skip completed cells.")
    p.add_argument("--base-seed", type=int, default=0, help="Base seed used to derive deterministic per-cell seeds.")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_phase_sweep"))
    return p.parse_args()


def main():
    args = parse_args()
    strategies = parse_list(args.strategies, str)
    distances = parse_list(args.distances, float)
    etas = parse_list(args.etas, float)
    seeds = parse_list(args.seeds, int)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "phase_raw.csv"
    raw_headers = [
        "distance",
        "eta",
        "strategy",
        "seed",
        "num_trials",
        "satisfied",
        "availability_req",
        "mean_t_success",
        "deadline_s",
        "deadline_ps",
        "setup_slack_s",
        "status",
        "error",
    ]
    done = set()
    if args.resume and raw_path.exists():
        with raw_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status", "ok") == "ok":
                    done.add((float(row["distance"]), float(row["eta"]), row["strategy"], int(row["seed"])))

    def cell_seed(strategy: str, distance: float, eta: float, seed: int) -> int:
        key = f"{strategy}:{distance}:{eta}:{seed}:{args.base_seed}"
        val = int.from_bytes(hashlib.md5(key.encode()).digest()[:8], "big") % (2**31)
        return args.base_seed + val

    tasks = []
    for dist in distances:
        for eta in etas:
            for strategy in strategies:
                for seed in seeds:
                    key = (dist, eta, strategy, seed)
                    if key in done:
                        continue
                    tasks.append(key)

    mode = "a" if raw_path.exists() else "w"
    with raw_path.open(mode, newline="") as f_raw:
        writer = csv.writer(f_raw)
        if mode == "w":
            writer.writerow(raw_headers)
            f_raw.flush()

        def run_cell(key):
            dist, eta, strat, seed = key
            try:
                ns = build_args(args, strat, dist, eta, seed)
                ns.seed = cell_seed(strat, dist, eta, seed)
                res = run_trials(ns)
                return (
                    dist,
                    eta,
                    strat,
                    seed,
                    res["num_trials"],
                    res["satisfied"],
                    res["availability_req"],
                    res["mean_t_success"],
                    res["deadline_s"],
                    res["deadline_ps"],
                    res["setup_slack_s"],
                    "ok",
                    "",
                )
            except Exception as e:  # noqa: BLE001
                return (
                    dist,
                    eta,
                    strat,
                    seed,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "error",
                    str(e),
                )

        results: List[Tuple] = []
        if tasks:
            max_workers = min(args.workers, 4)
            if max_workers <= 1:
                for t in tasks:
                    row = run_cell(t)
                    writer.writerow(row)
                    f_raw.flush()
                    if row[-2] == "ok":
                        results.append(row)
            else:
                try:
                    with ProcessPoolExecutor(max_workers=max_workers) as ex:
                        future_map = {ex.submit(run_cell, t): t for t in tasks}
                        for fut in as_completed(future_map):
                            row = fut.result()
                            writer.writerow(row)
                            f_raw.flush()
                            if row[-2] == "ok":
                                results.append(row)
                except PermissionError:
                    # Fallback to serial if process pool is not permitted
                    for t in tasks:
                        row = run_cell(t)
                        writer.writerow(row)
                        f_raw.flush()
                        if row[-2] == "ok":
                            results.append(row)
        else:
            with raw_path.open() as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("status", "ok") == "ok":
                        results.append(
                            (
                                float(row["distance"]),
                                float(row["eta"]),
                                row["strategy"],
                                int(row["seed"]),
                                int(row["num_trials"]),
                                int(row["satisfied"]),
                                float(row["availability_req"]),
                                float(row["mean_t_success"]),
                                float(row["deadline_s"]),
                                float(row["deadline_ps"]),
                                float(row["setup_slack_s"]),
                                "ok",
                                "",
                            )
                        )

    agg_headers = [
        "distance",
        "eta",
        "strategy",
        "runs",
        "availability_mean",
        "availability_std",
        "availability_ci95",
        "deadline_s",
        "deadline_ps",
        "setup_slack_s",
        "runs_failed",
    ]
    agg_rows = []
    agg_map: Dict[Tuple[float, float, str], List[float]] = defaultdict(list)
    meta_map: Dict[Tuple[float, float, str], Tuple[float, float, float]] = {}
    fail_counts = defaultdict(int)
    for row in results:
        key = (row[0], row[1], row[2])
        agg_map[key].append(row[6])
        meta_map[key] = (row[8], row[9], row[10])
    if raw_path.exists():
        with raw_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("status", "ok") != "ok":
                    key = (float(row["distance"]), float(row["eta"]), row["strategy"])
                    fail_counts[key] += 1

    for key, vals in agg_map.items():
        dist, eta, strategy = key
        n = len(vals)
        mean = float(np.mean(vals)) if vals else 0.0
        std = float(np.std(vals, ddof=0)) if vals else 0.0
        dl_s, dl_ps, slack = meta_map.get(key, (None, None, None))
        agg_rows.append(
            (
                dist,
                eta,
                strategy,
                n,
                mean,
                std,
                ci95(std, n),
                dl_s,
                dl_ps,
                slack,
                fail_counts.get(key, 0),
            )
        )
    write_csv(out_dir / "phase_agg.csv", agg_headers, agg_rows)
    print(f"Wrote raw to {out_dir/'phase_raw.csv'}")
    print(f"Wrote agg to {out_dir/'phase_agg.csv'}")


if __name__ == "__main__":
    main()
