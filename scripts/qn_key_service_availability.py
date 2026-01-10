"""CLI for key-service availability on NSFNET."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_experiment_presets import apply_preset
from scripts.qn_topologies import nsfnet_topology
from sequence.qn.key_service import simulate_key_service
from sequence.qn.parallel import normalize_workers


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Key-service availability simulator (OTP/session).")
    p.add_argument("--topology", choices=["nsfnet"], default="nsfnet")
    p.add_argument("--strategy", choices=["BK", "DQT", "EQT"], default="BK")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--horizon-s", type=float, default=1.0)
    p.add_argument("--lambda-req", type=float, default=1.0)
    p.add_argument("--tau-s", type=float, default=0.1)
    p.add_argument("--crypto-model", choices=["otp", "session"], default="otp")
    p.add_argument("--otp-data-rate-bps", type=float, default=1e3)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--session-key-bits", type=int, default=1024)
    p.add_argument("--kmax-bits", type=float, default=1e6)
    p.add_argument("--base-key-rate-bps", type=float, default=1e5)
    p.add_argument("--strategy-params", type=json.loads, default="{}", help="JSON dict")
    p.add_argument("--routing", choices=["shortest"], default="shortest")
    p.add_argument("--allow-wait", action="store_true", default=True)
    p.add_argument("--reserve-mode", choices=["upfront"], default="upfront")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_key_service"))
    p.add_argument("--resume", action="store_true", help="Append incremental raw logs.")
    p.add_argument("--preset", type=str, default="", help="Named preset for key-service runs.")
    p.add_argument("--workers", type=int, default=2, help="Reserved for future parallelism (2..20).")
    return p.parse_args()


def main():
    args = parse_args()
    args = apply_preset(args, args.preset)
    topo = nsfnet_topology()
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = out_dir / "requests_raw.csv"
    summary_path = out_dir / "summary.json"

    result = simulate_key_service(
        topo,
        strategy=args.strategy,
        seed=args.seed,
        horizon_s=args.horizon_s,
        lambda_req=args.lambda_req,
        tau_s=args.tau_s,
        crypto_model=args.crypto_model,
        otp_data_rate_bps=args.otp_data_rate_bps,
        otp_session_duration_s=args.otp_session_duration_s,
        session_key_bits=args.session_key_bits,
        kmax_bits=args.kmax_bits,
        base_key_rate_bps=args.base_key_rate_bps,
        strategy_params=args.strategy_params,
        routing=args.routing,
        allow_wait=args.allow_wait,
        reserve_mode=args.reserve_mode,
    )

    headers = [
        "t_arrival",
        "t_start",
        "served",
        "wait",
        "src",
        "dst",
        "hops",
        "bits",
        "path",
    ]
    mode = "a" if (args.resume and raw_path.exists()) else "w"
    with raw_path.open(mode, newline="") as f:
        writer = csv.writer(f)
        if mode == "w":
            writer.writerow(headers)
        for log in result["logs"]:
            writer.writerow(
                [
                    log.t_arrival,
                    log.t_start,
                    log.served,
                    log.wait if not math.isinf(log.wait) else "inf",
                    log.src,
                    log.dst,
                    log.hops,
                    log.bits,
                    ";".join([f"{a}-{b}" for a, b in log.path]),
                ]
            )

    summary = result.copy()
    summary.pop("logs", None)
    try:
        effective_workers, cpu_limit, cpu_reason = normalize_workers(args.workers, min_workers=2, max_workers=20)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    if cpu_limit is not None and effective_workers < args.workers:
        print(f"WARNING: cpu_limit={cpu_limit:.2f} ({cpu_reason}); effective_workers={effective_workers}")
    summary["effective_workers"] = effective_workers
    with summary_path.open("w") as f:
        json.dump(summary, f, indent=2)
    print(f"Wrote {raw_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
