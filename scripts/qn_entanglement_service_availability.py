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
from scripts.qn_topologies import nsfnet_edges, load_edge_distances_csv, load_distance_dataset
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service
from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, swap_params_for_strategy


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
    p.add_argument("--eta", type=float, default=0.8)
    p.add_argument("--attempt-rate-opt-hz", type=float, default=1e5)
    p.add_argument("--attempt-rate-sc-hz", type=float, default=1e5)
    p.add_argument("--p-bsm-opt", type=float, default=0.9)
    p.add_argument("--p-bsm-sc", type=float, default=0.95)
    p.add_argument("--coherence-opt-s", type=float, default=0.02)
    p.add_argument("--coherence-sc-s", type=float, default=0.03)
    p.add_argument("--swap-latency-s", type=float, default=0.0)
    p.add_argument("--transduction-latency-s", type=float, default=0.0)
    p.add_argument("--key-bits-per-pair", type=float, default=1.0)
    p.add_argument("--key-bits-per-pair-list", type=str, default="", help="Optional list; if set, run all values.")
    p.add_argument("--otp-data-rate-bps", type=float, default=1e3)
    p.add_argument("--otp-session-duration-s", type=float, default=0.01)
    p.add_argument("--otp-directions", type=int, default=2)
    p.add_argument("--edge-params-csv", type=Path, default=None, help="CSV with u,v,attempt_rate_hz,p_eg,coherence_time_s")
    p.add_argument("--edge-distance-csv", type=Path, default=None, help="CSV with u,v,distance_m for NSFNET")
    p.add_argument(
        "--distance-dataset-id",
        type=str,
        default="sndlib_great_circle_heuristic",
        help="Distance dataset id (sndlib_great_circle_heuristic | topologybench_nsfnet13)",
    )
    p.add_argument("--p-eg-per-km", type=float, default=None, help="If set with distance map, compute p_eg=exp(-loss_db_per_km*dist_km) using loss_db_per_km= -10*log10(p_eg_per_km)")
    p.add_argument("--loss-db-per-km", type=float, default=0.2, help="Loss in dB/km for distance->p_eg mapping")
    p.add_argument("--upgrade-k", type=int, default=0, help="Top-k edges to upgrade to QT params (nsfnet only).")
    p.add_argument("--upgrade-policy", choices=["shortestpath_count", "betweenness"], default="shortestpath_count")
    p.add_argument("--upgrade-mode", choices=["edges", "repeaters"], default="edges")
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
    dist_map = {}
    if args.topology == "nsfnet":
        dist_map = load_distance_dataset(args.distance_dataset_id)
    if args.edge_distance_csv:
        dist_map = load_edge_distances_csv(args.edge_distance_csv)

    knobs = StrategyKnobs(
        attempt_rate_opt_hz=args.attempt_rate_opt_hz,
        attempt_rate_sc_hz=args.attempt_rate_sc_hz,
        p_bsm_opt=args.p_bsm_opt,
        p_bsm_sc=args.p_bsm_sc,
        coherence_opt_s=args.coherence_opt_s,
        coherence_sc_s=args.coherence_sc_s,
        loss_db_per_km=args.loss_db_per_km,
        p_eg_per_km=args.p_eg_per_km,
        transduction_latency_s=args.transduction_latency_s,
        swap_latency_s=args.swap_latency_s,
    )

    def rank_edges():
        topo = {n: [] for n in set([n for e in dist_map for n in e])}
        if not topo:
            for a, b in nsfnet_edges():
                topo.setdefault(a, []).append(b)
                topo.setdefault(b, []).append(a)
        counts = {}
        for a in topo:
            from collections import deque

            for b in topo:
                if a >= b:
                    continue
                q = deque([[a]])
                seen = {a}
                path_found = None
                while q:
                    pth = q.popleft()
                    n = pth[-1]
                    if n == b:
                        path_found = pth
                        break
                    for nei in topo.get(n, []):
                        if nei not in seen:
                            seen.add(nei)
                            q.append(pth + [nei])
                if not path_found:
                    continue
                for i in range(len(path_found) - 1):
                    e = tuple(sorted((path_found[i], path_found[i + 1])))
                    counts[e] = counts.get(e, 0) + 1
        ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
        return [e for e, _ in ranked]

    if args.upgrade_mode != "edges":
        raise SystemExit("upgrade-mode repeaters not implemented; use edges")
    ranked_edges = rank_edges()
    upgrade_edges = set(ranked_edges[: args.upgrade_k]) if args.topology == "nsfnet" else set()

    edge_params = {}
    for e in edges:
        dist_km = dist_map.get(e, 1000.0) / 1000.0 if dist_map else 1.0
        use_strategy = args.strategy if e in upgrade_edges else "BK"
        p_eg, attempt_rate, coherence, p_bsm, extra_lat = edge_params_for_strategy(use_strategy, dist_km, args.eta, knobs)
        edge_params[e] = EdgeParams(attempt_rate_hz=attempt_rate, p_eg=p_eg, coherence_time_s=coherence, extra_latency_s=extra_lat)
    swap_p, swap_lat = swap_params_for_strategy(args.strategy, knobs)
    swap_params = SwapParams(p_bsm=swap_p, latency_s=swap_lat)

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
            "distance_dataset_id": args.distance_dataset_id,
            "upgrade_edges": sorted(list(upgrade_edges)),
            "strategy": args.strategy,
            "eta": args.eta,
        }
        summary_path.write_text(json.dumps(summary, indent=2))
        print(f"Wrote raw to {raw_path}")
        print(f"Wrote summary to {summary_path}")


if __name__ == "__main__":
    main()
