"""Sweep key-service availability over lambda (and optional Kmax) for strategies."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_experiment_presets import apply_preset
from scripts.qn_topologies import nsfnet_topology
from sequence.qn.key_service import simulate_key_service
from sequence.qn.parallel import normalize_workers


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def ci95(std: float, n: int) -> float:
    if n <= 0:
        return 0.0
    return 1.96 * std / math.sqrt(n)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Key-service sweep over lambda and Kmax.")
    p.add_argument("--strategies", default="BK,DQT,EQT")
    p.add_argument("--lambdas", default="1.0,5.0,10.0")
    p.add_argument("--kmax-list", default="1e5")
    p.add_argument("--seeds", default="0,1,2")
    p.add_argument("--num-trials", type=int, default=10, help="Requests per seed? Actually horizon-driven; kept for consistency.")
    p.add_argument("--topology", choices=["nsfnet"], default="nsfnet")
    p.add_argument("--horizon-s", type=float, default=1.0)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--crypto-model", choices=["otp", "session"], default="otp")
    p.add_argument("--otp-data-rate-bps", type=float, default=1e3)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--session-key-bits", type=int, default=1024)
    p.add_argument("--base-key-rate-bps", type=float, default=1e5)
    p.add_argument("--strategy-params", type=json.loads, default="{}", help="JSON dict")
    p.add_argument("--link-rate-json", type=Path, default=None, help="JSON mapping edge->rate_bps (edge as 'A-B').")
    p.add_argument("--link-rate-csv", type=Path, default=None, help="CSV with edge,rate_bps columns.")
    p.add_argument("--routing", choices=["shortest"], default="shortest")
    p.add_argument("--allow-wait", action="store_true", default=True)
    p.add_argument("--reserve-mode", choices=["upfront"], default="upfront")
    p.add_argument("--preset", type=str, default="", help="Named preset.")
    p.add_argument("--workers", type=int, default=2, help="Parallel workers (2..20).")
    p.add_argument("--base-seed", type=int, default=0)
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_key_service_sweep"))
    p.add_argument("--resume", action="store_true", help="Resume from raw CSV.")
    return p.parse_args()


def load_link_rates(args: argparse.Namespace) -> Dict[Tuple[str, str], float]:
    rates = {}
    if args.link_rate_json and args.link_rate_json.exists():
        data = json.loads(args.link_rate_json.read_text())
        for k, v in data.items():
            a, b = k.split("-")
            rates[(a, b)] = float(v)
    if args.link_rate_csv and args.link_rate_csv.exists():
        with args.link_rate_csv.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                edge = row.get("edge") or row.get("link")
                if not edge:
                    continue
                a, b = edge.split("-")
                rates[(a, b)] = float(row["rate_bps"])
    return rates


def main():
    args = parse_args()
    args = apply_preset(args, args.preset)
    strategies = parse_list(args.strategies, str)
    lambdas = parse_list(args.lambdas, float)
    kmax_list = parse_list(args.kmax_list, float)
    seeds = parse_list(args.seeds, int)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "key_service_sweep_raw.csv"

    topo = nsfnet_topology()
    link_rates = load_link_rates(args)

    raw_headers = [
        "strategy",
        "lambda",
        "kmax",
        "seed",
        "availability",
        "block_prob",
        "served",
        "total",
        "mean_wait",
        "mean_hops",
    ]
    done = set()
    if args.resume and raw_path.exists():
        with raw_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                done.add((row["strategy"], float(row["lambda"]), float(row["kmax"]), int(row["seed"])))

    def cell_seed(strategy: str, lamb: float, kmax: float, seed: int) -> int:
        key = f"{strategy}:{lamb}:{kmax}:{seed}:{args.base_seed}"
        return args.base_seed + int.from_bytes(hashlib.md5(key.encode()).digest()[:8], "big") % (2**31)

    tasks = []
    for strat in strategies:
        for lamb in lambdas:
            for kmax in kmax_list:
                for seed in seeds:
                    key = (strat, lamb, kmax, seed)
                    if key in done:
                        continue
                    tasks.append(key)

    def run_cell(key):
        strat, lamb, kmax, seed = key
        res = simulate_key_service(
            topo,
            strategy=strat,
            seed=cell_seed(strat, lamb, kmax, seed),
            horizon_s=args.horizon_s,
            lambda_req=lamb,
            tau_s=args.tau_s,
            crypto_model=args.crypto_model,
            otp_data_rate_bps=args.otp_data_rate_bps,
            otp_session_duration_s=args.otp_session_duration_s,
            session_key_bits=args.session_key_bits,
            kmax_bits=kmax,
            base_key_rate_bps=args.base_key_rate_bps,
            strategy_params=args.strategy_params,
            routing=args.routing,
            allow_wait=args.allow_wait,
            reserve_mode=args.reserve_mode,
            link_rates=link_rates,
            otp_directions=args.otp_directions,
        )
        return (
            strat,
            lamb,
            kmax,
            seed,
            res["availability"],
            res["block_prob"],
            res["served"],
            res["total"],
            res["mean_wait"],
            res["mean_hops"],
        )

    results = []
    if tasks:
        try:
            effective_workers, cpu_limit, cpu_reason = normalize_workers(args.workers, min_workers=2, max_workers=20)
        except RuntimeError as exc:
            raise SystemExit(str(exc)) from exc
        if cpu_limit is not None and effective_workers < args.workers:
            print(f"WARNING: cpu_limit={cpu_limit:.2f} ({cpu_reason}); effective_workers={effective_workers}")
        print(f"Using pool_kind=process effective_workers={effective_workers} task_count={len(tasks)} chunksize=1")
        with ProcessPoolExecutor(max_workers=effective_workers) as ex:
            future_map = {ex.submit(run_cell, t): t for t in tasks}
            for fut in as_completed(future_map):
                results.append(fut.result())

    mode = "a" if (args.resume and raw_path.exists()) else "w"
    with raw_path.open(mode, newline="") as f_raw:
        writer = csv.writer(f_raw)
        if mode == "w":
            writer.writerow(raw_headers)
        for row in results:
            writer.writerow(row)
        f_raw.flush()

    agg = defaultdict(list)
    all_rows = []
    if raw_path.exists():
        with raw_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    mw = float(row["mean_wait"]) if row.get("mean_wait") not in ("", None) else 0.0
                    mh = float(row["mean_hops"]) if row.get("mean_hops") not in ("", None) else 0.0
                except Exception:
                    mw, mh = 0.0, 0.0
                all_rows.append(
                    (
                        row["strategy"],
                        float(row["lambda"]),
                        float(row["kmax"]),
                        int(row["seed"]),
                        float(row["availability"]),
                        float(row["block_prob"]),
                        int(row["served"]),
                        int(row["total"]),
                        mw,
                        mh,
                    )
                )
    for r in all_rows:
        key = (r[0], r[1], r[2])
        agg[key].append(r)

    agg_rows = []
    for key, vals in agg.items():
        strat, lamb, kmax = key
        avails = [v[4] for v in vals]
        blocks = [v[5] for v in vals]
        mean = float(np.mean(avails)) if avails else 0.0
        std = float(np.std(avails, ddof=0)) if avails else 0.0
        mean_block = float(np.mean(blocks)) if blocks else 0.0
        agg_rows.append(
            (
                strat,
                lamb,
                kmax,
                len(vals),
                mean,
                std,
                ci95(std, len(vals)),
                mean_block,
            )
        )
    agg_headers = ["strategy", "lambda", "kmax", "runs", "availability_mean", "availability_std", "availability_ci95", "block_prob_mean"]
    with (out_dir / "key_service_sweep_agg.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(agg_headers)
        writer.writerows(agg_rows)
    print(f"Wrote {raw_path}")
    print(f"Wrote {out_dir / 'key_service_sweep_agg.csv'}")


if __name__ == "__main__":
    main()
