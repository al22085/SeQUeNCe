"""CLI for entanglement service availability (EG+memory+swapping with retries)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_experiment_presets import apply_preset
from scripts.qn_topologies import nsfnet_edges, load_edge_distances_csv
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service


def parse_list(raw: str, cast=float) -> List:
    return [cast(x) for x in raw.split(",") if x]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Entanglement service availability with discrete-event EG + swapping retries.")
    p.add_argument("--topology", choices=["chain", "nsfnet"], default="chain")
    p.add_argument("--strategy", choices=["BK", "DQT", "EQT"], default="BK")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--seeds", type=str, default="")
    p.add_argument("--num-requests", type=int, default=20)
    p.add_argument("--lambda-req", type=float, default=None, help="If set, use Poisson arrivals; otherwise spread num-requests across horizon.")
    p.add_argument("--horizon-s", type=float, default=0.1)
    p.add_argument("--tau-s", type=float, default=0.05)
    p.add_argument("--attempt-rate-hz", type=float, default=1e5)
    p.add_argument("--p-eg", type=float, default=0.2)
    p.add_argument("--coherence-time-s", type=float, default=0.02)
    p.add_argument("--p-bsm", type=float, default=0.9)
    p.add_argument("--swap-latency-s", type=float, default=0.0)
    p.add_argument("--key-bits-per-pair", type=float, default=1.0)
    p.add_argument("--key-bits-per-pair-list", type=str, default="", help="Optional list; if set, run all values.")
    p.add_argument("--otp-data-rate-bps", type=float, default=1e3)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--edge-params-csv", type=Path, default=None, help="CSV with u,v,attempt_rate_hz,p_eg,coherence_time_s")
    p.add_argument("--edge-distance-csv", type=Path, default=None, help="CSV with u,v,distance_m for NSFNET")
    p.add_argument("--p-eg-per-km", type=float, default=None, help="If set with distance map, compute p_eg=exp(-loss_db_per_km*dist_km) using loss_db_per_km= -10*log10(p_eg_per_km)")
    p.add_argument("--loss-db-per-km", type=float, default=0.2, help="Loss in dB/km for distance->p_eg mapping")
    p.add_argument("--preset", type=str, default="")
    p.add_argument("--workers", type=int, default=1, help="Parallel workers (capped at 4).")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_entanglement_service"))
    p.add_argument("--resume", action="store_true")
    return p.parse_args()


def build_path(topology: str) -> List[str]:
    if topology == "chain":
        path = ["A", "R1", "R2", "B"]
    else:
        path = ["1", "2", "3", "4"]
    return path


def main():
    args = parse_args()
    args = apply_preset(args, args.preset)
    seeds = parse_list(args.seeds, int) if args.seeds else [args.seed]
    path = build_path(args.topology)
    edges = [tuple(sorted((path[i], path[i + 1]))) for i in range(len(path) - 1)]
    edge_params = {}
    dist_map = {}
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)

    if args.edge_params_csv and args.edge_params_csv.exists():
        with args.edge_params_csv.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                e = tuple(sorted((row["u"], row["v"])))
                edge_params[e] = EdgeParams(
                    attempt_rate_hz=float(row["attempt_rate_hz"]),
                    p_eg=float(row["p_eg"]),
                    coherence_time_s=float(row["coherence_time_s"]),
                )
    for e in edges:
        if e in edge_params:
            continue
        p_eg = args.p_eg
        if dist_map and args.p_eg_per_km is not None:
            dist_km = dist_map.get(e, 1000.0) / 1000.0
            attn_db = args.loss_db_per_km * dist_km
            p_eg = math.exp(-attn_db * math.log(10) / 10.0)
        edge_params[e] = EdgeParams(attempt_rate_hz=args.attempt_rate_hz, p_eg=p_eg, coherence_time_s=args.coherence_time_s)
    swap_params = SwapParams(p_bsm=args.p_bsm, latency_s=args.swap_latency_s)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    kbits_list = parse_list(args.key_bits_per_pair_list, float) if args.key_bits_per_pair_list else [args.key_bits_per_pair]

    for kb in kbits_list:
        subdir = out_dir / f"kbits_{kb}"
        subdir.mkdir(parents=True, exist_ok=True)
        raw_path = subdir / "entanglement_service_raw.csv"
        summary_path = subdir / "summary.json"
        raw_headers = [
            "seed",
            "request_idx",
            "arrival_s",
            "deadline_s",
            "served",
            "t_done_s",
            "bits_needed",
        ]
        mode = "a" if (args.resume and raw_path.exists()) else "w"
        with raw_path.open(mode, newline="") as f_raw:
            writer = csv.writer(f_raw)
            if mode == "w":
                writer.writerow(raw_headers)

            availabilities = []
            for s in seeds:
                res = simulate_entanglement_service(
                    path,
                    edge_params,
                    swap_params,
                    seed=s,
                    horizon_s=args.horizon_s,
                    tau_s=args.tau_s,
                    num_requests=args.num_requests if args.lambda_req is None else None,
                    lambda_req=args.lambda_req,
                    otp_data_rate_bps=args.otp_data_rate_bps,
                    otp_session_duration_s=args.otp_session_duration_s,
                    otp_directions=args.otp_directions,
                    key_bits_per_pair=kb,
                )
                availabilities.append(res["availability"])
                for idx, req in enumerate(res["requests"]):
                    writer.writerow(
                        [
                            s,
                            idx,
                            req.t_arrival,
                            req.deadline,
                            req.served,
                            req.t_done if req.t_done is not None else "",
                            req.bits_needed,
                        ]
                    )
            f_raw.flush()

        availability_mean = float(sum(availabilities) / len(availabilities)) if availabilities else 0.0
        summary = {
            "availability_mean": availability_mean,
            "key_bits_per_pair": kb,
            "seeds": seeds,
            "targets": {tgt: availability_mean >= tgt for tgt in (0.9, 0.99, 0.999)},
        }
        summary_path.write_text(json.dumps(summary, indent=2))
        print(f"Wrote raw to {raw_path}")
        print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
