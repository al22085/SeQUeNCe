#!/usr/bin/env python3
"""Run eta-threshold availability jobs in batches and aggregate results.

Note: eta is passed into strategy params (p_eg depends on eta).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
AVAILABILITY_SCRIPT = ROOT / "scripts" / "qn_entanglement_service_availability.py"
COMPUTE_AVAILABILITY = ROOT / "scripts" / "compute_availability.py"

REQUIRED_RAW_COLUMNS = {"src", "dst", "arrival_s", "deadline_s", "served", "t_done_s"}
SCENARIO_ORDER = ["BK", "EQT"]
DEFAULT_BASELINE = {
    "topology": "chain",
    "pair_mode": "fixed",
    "src_node": "A",
    "dst_node": "B",
    "horizon_s": 0.1,
    "tau_s": 0.05,
    "lambda_req": None,
    "otp_data_rate_bps": 1e3,
    "otp_session_duration_s": 0.01,
    "otp_directions": 2,
    "distance_dataset_id": "sndlib_great_circle_heuristic",
    "edge_distance_csv": None,
    "segment_length_km": 50.0,
    "key_bits_per_pair": 1.0,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run eta threshold availability study in batches.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("scripts/eta_threshold_config.json"),
        help="JSON config with eta sweep list.",
    )
    parser.add_argument("--eta", type=float, action="append", default=[], help="Eta value to run.")
    parser.add_argument("--etas", type=str, default="", help="Comma-separated eta list.")
    parser.add_argument("--scenarios", type=str, default="BK,EQT", help="Comma-separated scenarios.")
    parser.add_argument("--seed-start", type=int, default=0, help="Start seed (inclusive).")
    parser.add_argument("--seed-end", type=int, default=30, help="End seed (exclusive).")
    parser.add_argument("--workers", type=int, default=20, help="Parallel workers (max 20).")
    parser.add_argument("--requests-per-seed", type=int, default=200, help="Requests per seed.")
    parser.add_argument("--bk-eta", type=float, default=None, help="Eta used for BK runs.")
    parser.add_argument(
        "--measured-eta",
        type=float,
        default=None,
        help="Eta used for \\BKAvailAtMeasured/\\EQTAvailAtMeasured macros.",
    )
    parser.add_argument(
        "--outdir", type=Path, default=Path("out/study_eta_threshold"), help="Study output dir."
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=Path("out/paper_artifacts"),
        help="Paper artifacts directory.",
    )
    parser.add_argument("--resume", action="store_true", help="Skip jobs with existing summaries.")
    parser.add_argument(
        "--aggregate-only", action="store_true", help="Only aggregate existing summaries."
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Keep temporary run directories (for debugging).",
    )
    parser.add_argument("--force", action="store_true", help="Re-run even if raw CSV exists.")
    parser.add_argument("--topology", type=str, default=None, help="Topology (chain|nsfnet).")
    parser.add_argument("--pair-mode", type=str, default=None, help="Pair mode (fixed|random).")
    parser.add_argument("--src-node", type=str, default=None, help="Source node (fixed mode).")
    parser.add_argument("--dst-node", type=str, default=None, help="Destination node (fixed mode).")
    parser.add_argument("--horizon-s", type=float, default=None, help="Request horizon in seconds.")
    parser.add_argument("--tau-s", type=float, default=None, help="Deadline window in seconds.")
    parser.add_argument("--lambda-req", type=float, default=None, help="Poisson arrival rate.")
    parser.add_argument("--otp-data-rate-bps", type=float, default=None, help="OTP data rate.")
    parser.add_argument(
        "--otp-session-duration-s", type=float, default=None, help="OTP session duration."
    )
    parser.add_argument("--otp-directions", type=int, default=None, help="OTP directions.")
    parser.add_argument("--distance-dataset-id", type=str, default=None, help="Distance dataset id.")
    parser.add_argument("--edge-distance-csv", type=Path, default=None, help="Edge distance CSV.")
    parser.add_argument(
        "--segment-length-km", type=float, default=None, help="Segment length for nsfnet."
    )
    parser.add_argument(
        "--key-bits-per-pair", type=float, default=None, help="Key bits per pair."
    )
    return parser.parse_args()


def iter_seeds(start: int, end: int) -> Iterable[int]:
    if end <= start:
        raise ValueError("seed-end must be greater than seed-start")
    return range(start, end)


def parse_list(raw: str) -> list[float]:
    if not raw:
        return []
    return [float(x) for x in raw.split(",") if x.strip()]


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def load_etas(args: argparse.Namespace, config: dict) -> list[float]:
    if args.eta:
        return sorted(set(args.eta))
    if args.etas:
        return sorted(set(parse_list(args.etas)))
    etas = config.get("etas", [])
    if not etas:
        raise ValueError("No etas found in config.")
    return [float(x) for x in etas]


def resolve_bk_eta(args: argparse.Namespace, config: dict, etas: list[float]) -> float:
    if args.bk_eta is not None:
        return float(args.bk_eta)
    if "bk_eta" in config:
        return float(config["bk_eta"])
    return float(etas[-1])


def resolve_measured_eta(args: argparse.Namespace, config: dict, etas: list[float]) -> float:
    if args.measured_eta is not None:
        return float(args.measured_eta)
    if "measured_eta" in config:
        return float(config["measured_eta"])
    return float(etas[0])


def resolve_baseline(args: argparse.Namespace, config: dict) -> dict:
    baseline = dict(DEFAULT_BASELINE)
    baseline.update(config.get("baseline", {}))
    overrides = {
        "topology": args.topology,
        "pair_mode": args.pair_mode,
        "src_node": args.src_node,
        "dst_node": args.dst_node,
        "horizon_s": args.horizon_s,
        "tau_s": args.tau_s,
        "lambda_req": args.lambda_req,
        "otp_data_rate_bps": args.otp_data_rate_bps,
        "otp_session_duration_s": args.otp_session_duration_s,
        "otp_directions": args.otp_directions,
        "distance_dataset_id": args.distance_dataset_id,
        "edge_distance_csv": args.edge_distance_csv,
        "segment_length_km": args.segment_length_km,
        "key_bits_per_pair": args.key_bits_per_pair,
    }
    for key, value in overrides.items():
        if value is not None:
            baseline[key] = value
    return baseline


def format_eta(eta: float) -> str:
    return f"{eta:.5f}"


def parse_served(raw: str | None) -> bool:
    if raw is None:
        return False
    text = str(raw).strip().lower()
    if text in ("1", "true", "t", "yes", "y"):
        return True
    if text in ("0", "false", "f", "no", "n", ""):
        return False
    try:
        return float(text) != 0.0
    except ValueError as exc:
        raise ValueError(f"Unrecognized served value: {raw}") from exc


def normalize_raw(raw_csv: Path, requests_csv: Path, printed_header: list[bool]) -> None:
    requests_csv.parent.mkdir(parents=True, exist_ok=True)
    with raw_csv.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = REQUIRED_RAW_COLUMNS - set(fieldnames)
        if missing:
            missing_list = ", ".join(sorted(missing))
            raise ValueError(f"Missing raw columns in {raw_csv}: {missing_list}")
        if not printed_header[0]:
            print(f"Raw columns: {fieldnames}")
            print("Mapping: src=src, dst=dst, t_start=arrival_s, deadline=deadline_s, t_finish=t_done_s")
            printed_header[0] = True

        rows = []
        for row in reader:
            src = row.get("src", "")
            dst = row.get("dst", "")
            t_start = float(row["arrival_s"])
            deadline = float(row["deadline_s"])
            served = parse_served(row.get("served"))
            t_done_raw = row.get("t_done_s", "")
            t_done = float(t_done_raw) if str(t_done_raw).strip() not in ("", "None") else None
            success = int(served and t_done is not None and t_done <= deadline)
            t_finish = "" if success == 0 else f"{t_done}"
            rows.append(
                {
                    "request_id": row.get("request_idx", ""),
                    "src": src,
                    "dst": dst,
                    "t_start": f"{t_start}",
                    "deadline": f"{deadline}",
                    "success": f"{success}",
                    "t_finish": t_finish,
                    "_sort": (t_start, src, dst),
                }
            )

    has_request_idx = any(r["request_id"] for r in rows)
    if not has_request_idx:
        rows.sort(key=lambda r: r["_sort"])
        for idx, row in enumerate(rows):
            row["request_id"] = str(idx)

    with requests_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["request_id", "src", "dst", "t_start", "deadline", "success", "t_finish"])
        for row in rows:
            writer.writerow(
                [
                    row["request_id"],
                    row["src"],
                    row["dst"],
                    row["t_start"],
                    row["deadline"],
                    row["success"],
                    row["t_finish"],
                ]
            )


def build_sim_command(
    *,
    scenario: str,
    eta: float,
    seed: int,
    workers: int,
    requests_per_seed: int,
    temp_dir: Path,
    baseline: dict,
) -> list[str]:
    cmd = [
        sys.executable,
        str(AVAILABILITY_SCRIPT),
        "--topology",
        str(baseline["topology"]),
        "--strategy",
        scenario,
        "--seed",
        str(seed),
        "--num-requests",
        str(requests_per_seed),
        "--eta",
        str(eta),
        "--workers",
        str(workers),
        "--horizon-s",
        str(baseline["horizon_s"]),
        "--tau-s",
        str(baseline["tau_s"]),
        "--otp-data-rate-bps",
        str(baseline["otp_data_rate_bps"]),
        "--otp-session-duration-s",
        str(baseline["otp_session_duration_s"]),
        "--otp-directions",
        str(baseline["otp_directions"]),
        "--key-bits-per-pair",
        str(baseline["key_bits_per_pair"]),
        "--out-dir",
        str(temp_dir),
    ]
    if baseline.get("pair_mode"):
        cmd += ["--pair-mode", str(baseline["pair_mode"])]
    if baseline.get("src_node"):
        cmd += ["--src-node", str(baseline["src_node"])]
    if baseline.get("dst_node"):
        cmd += ["--dst-node", str(baseline["dst_node"])]
    if baseline.get("lambda_req") is not None:
        cmd += ["--lambda-req", str(baseline["lambda_req"])]
    if baseline.get("distance_dataset_id"):
        cmd += ["--distance-dataset-id", str(baseline["distance_dataset_id"])]
    if baseline.get("edge_distance_csv"):
        cmd += ["--edge-distance-csv", str(baseline["edge_distance_csv"])]
    if baseline.get("segment_length_km") is not None:
        cmd += ["--segment-length-km", str(baseline["segment_length_km"])]
    return cmd


def run_simulation(
    *,
    scenario: str,
    eta: float,
    seed: int,
    workers: int,
    requests_per_seed: int,
    temp_dir: Path,
    baseline: dict,
) -> None:
    temp_dir.mkdir(parents=True, exist_ok=True)
    cmd = build_sim_command(
        scenario=scenario,
        eta=eta,
        seed=seed,
        workers=workers,
        requests_per_seed=requests_per_seed,
        temp_dir=temp_dir,
        baseline=baseline,
    )
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)


def summarize_requests(requests_csv: Path, summary_dir: Path) -> None:
    cmd = [
        sys.executable,
        str(COMPUTE_AVAILABILITY),
        "--requests",
        str(requests_csv),
        "--outdir",
        str(summary_dir),
    ]
    subprocess.run(cmd, check=True)


def parse_tag(tag: str, prefix: str) -> str:
    if not tag.startswith(prefix):
        raise ValueError(f"Expected tag prefix '{prefix}' in {tag}")
    return tag[len(prefix) :]


def read_summary_csv(path: Path) -> tuple[float, int]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    if not rows:
        raise ValueError(f"Empty summary CSV: {path}")
    row = rows[0]
    return float(row["request_success_rate"]), int(row["n_requests"])


def aggregate_results(
    derived_root: Path, outdir: Path, artifacts_dir: Path, etas: list[float], bk_eta: float
) -> Path | None:
    rows: list[dict[str, object]] = []
    for summary_path in derived_root.rglob("summary.csv"):
        rel = summary_path.relative_to(derived_root)
        if len(rel.parts) < 3:
            continue
        scenario = rel.parts[0]
        eta = float(parse_tag(rel.parts[1], "eta_"))
        seed = int(parse_tag(rel.parts[2], "seed_"))
        if scenario == "BK" and eta != bk_eta:
            continue
        if scenario != "BK" and eta not in etas:
            continue
        success_rate, n_requests = read_summary_csv(summary_path)
        rows.append(
            {
                "scenario": scenario,
                "eta": eta,
                "seed": seed,
                "success_rate": success_rate,
                "n_requests": n_requests,
            }
        )

    if not rows:
        print("No summaries found to aggregate.")
        return None

    df = pd.DataFrame(rows)
    df["eta"] = df["eta"].astype(float)
    df["seed"] = df["seed"].astype(int)
    df["success_rate"] = df["success_rate"].astype(float)

    agg_rows: list[dict[str, object]] = []

    other_df = df[df["scenario"] != "BK"].copy()
    if not other_df.empty:
        agg_other = (
            other_df.groupby(["scenario", "eta"], as_index=False)
            .agg(
                n_seeds=("seed", "count"),
                n_requests_total=("n_requests", "sum"),
                mean_success_rate=("success_rate", "mean"),
                std_success_rate=("success_rate", "std"),
            )
            .sort_values(["scenario", "eta"])
        )
        agg_other["std_success_rate"] = agg_other["std_success_rate"].fillna(0.0)
        agg_rows.extend(agg_other.to_dict(orient="records"))

    bk_df = df[df["scenario"] == "BK"].copy()
    if not bk_df.empty:
        bk_group = bk_df.groupby(["scenario"], as_index=False).agg(
            n_seeds=("seed", "count"),
            n_requests_total=("n_requests", "sum"),
            mean_success_rate=("success_rate", "mean"),
            std_success_rate=("success_rate", "std"),
        )
        bk_group["std_success_rate"] = bk_group["std_success_rate"].fillna(0.0)
        bk_stats = bk_group.iloc[0].to_dict()
        for eta in etas:
            agg_rows.append(
                {
                    "scenario": "BK",
                    "eta": eta,
                    "n_seeds": int(bk_stats["n_seeds"]),
                    "n_requests_total": int(bk_stats["n_requests_total"]),
                    "mean_success_rate": float(bk_stats["mean_success_rate"]),
                    "std_success_rate": float(bk_stats["std_success_rate"]),
                }
            )
    else:
        print(f"WARNING: no BK summaries found (expected at eta={bk_eta})")

    agg = pd.DataFrame(agg_rows)
    if agg.empty:
        print("No aggregate rows produced.")
        return None

    agg["ci95_low"] = agg["mean_success_rate"] - 1.96 * agg["std_success_rate"] / agg["n_seeds"].pow(0.5)
    agg["ci95_high"] = agg["mean_success_rate"] + 1.96 * agg["std_success_rate"] / agg["n_seeds"].pow(0.5)
    agg["ci95_low"] = agg["ci95_low"].clip(lower=0.0, upper=1.0)
    agg["ci95_high"] = agg["ci95_high"].clip(lower=0.0, upper=1.0)

    agg["scenario"] = pd.Categorical(agg["scenario"], categories=SCENARIO_ORDER, ordered=True)
    agg = agg.sort_values(["scenario", "eta"]).reset_index(drop=True)

    outdir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_path = outdir / "results_eta_threshold.csv"
    artifacts_path = artifacts_dir / "results_eta_threshold.csv"
    agg.to_csv(out_path, index=False)
    agg.to_csv(artifacts_path, index=False)
    print(f"Wrote {out_path}")
    print(f"Wrote {artifacts_path}")
    return artifacts_path


def format_eta_value(value: float | None) -> str:
    if value is None:
        return "NA"
    text = f"{value:.3f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def format_metric_value(value: float | None, digits: int = 4) -> str:
    if value is None:
        return "NA"
    return f"{value:.{digits}f}"


def compute_thresholds(agg: pd.DataFrame, etas: list[float]) -> tuple[float | None, float | None]:
    if agg.empty:
        return None, None
    bk = agg[agg["scenario"] == "BK"].set_index("eta")
    eqt = agg[agg["scenario"] == "EQT"].set_index("eta")
    eta_equal = None
    eta_sig = None
    for eta in sorted(etas):
        if eta not in bk.index or eta not in eqt.index:
            continue
        if eta_equal is None and eqt.loc[eta, "mean_success_rate"] >= bk.loc[eta, "mean_success_rate"]:
            eta_equal = eta
        if eta_sig is None and eqt.loc[eta, "ci95_low"] >= bk.loc[eta, "ci95_high"]:
            eta_sig = eta
    return eta_equal, eta_sig


def lookup_metric(agg: pd.DataFrame, scenario: str, eta: float, column: str) -> float | None:
    rows = agg[(agg["scenario"] == scenario) & (agg["eta"].sub(eta).abs() < 1e-9)]
    if rows.empty:
        return None
    return float(rows.iloc[0][column])


def write_macros(
    path: Path,
    measured_eta: float,
    bk_measured: float | None,
    eqt_measured: float | None,
    eta_equal: float | None,
    eta_sig: float | None,
) -> None:
    lines = [
        "% Auto-generated by scripts/run_eta_threshold_batch.py",
        f"\\newcommand{{\\EtaMeasured}}{{{format_eta_value(measured_eta)}}}",
        f"\\newcommand{{\\BKAvailAtMeasured}}{{{format_metric_value(bk_measured)}}}",
        f"\\newcommand{{\\EQTAvailAtMeasured}}{{{format_metric_value(eqt_measured)}}}",
        f"\\newcommand{{\\EtaEqual}}{{{format_eta_value(eta_equal)}}}",
        f"\\newcommand{{\\EtaSig}}{{{format_eta_value(eta_sig)}}}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_readme(
    path: Path,
    etas: list[float],
    baseline: dict,
    bk_eta: float,
    measured_eta: float,
    eta_equal: float | None,
    eta_sig: float | None,
    seeds: tuple[int, int],
    requests_per_seed: int,
    workers: int,
) -> None:
    eta_list = ", ".join(format_eta_value(e) for e in etas)
    lines = [
        "# Eta-threshold study (BK vs EQT)",
        "",
        "Purpose",
        "- Determine the smallest transducer efficiency eta where EQT becomes comparable to BK.",
        "- Include experimental anchor points 0.087/0.15/0.30 (Sahu et al., Nat Commun 13, 1276 (2022)).",
        "",
        "Sweep",
        f"- etas: [{eta_list}]",
        f"- bk_eta (BK run reused): {format_eta_value(bk_eta)}",
        f"- measured_eta (macros): {format_eta_value(measured_eta)}",
        f"- seeds: {seeds[0]}..{seeds[1] - 1}",
        f"- requests/seed: {requests_per_seed}",
        f"- workers: {workers}",
        "",
        "Baseline simulator args (explicit)",
        f"- topology: {baseline.get('topology')}",
        f"- pair_mode: {baseline.get('pair_mode')}",
        f"- src_node: {baseline.get('src_node')}",
        f"- dst_node: {baseline.get('dst_node')}",
        f"- horizon_s: {baseline.get('horizon_s')}",
        f"- tau_s: {baseline.get('tau_s')}",
        f"- lambda_req: {baseline.get('lambda_req')}",
        f"- otp_data_rate_bps: {baseline.get('otp_data_rate_bps')}",
        f"- otp_session_duration_s: {baseline.get('otp_session_duration_s')}",
        f"- otp_directions: {baseline.get('otp_directions')}",
        f"- distance_dataset_id: {baseline.get('distance_dataset_id')}",
        f"- edge_distance_csv: {baseline.get('edge_distance_csv')}",
        f"- segment_length_km: {baseline.get('segment_length_km')}",
        f"- key_bits_per_pair: {baseline.get('key_bits_per_pair')}",
        "",
        "Diagnostic note",
        "- Earlier non-zero availability used chain topology (A->B) with horizon_s=0.1/tau_s=0.05.",
        "- The previous nsfnet-based eta sweep produced served=0 at all eta; this run reuses the non-zero baseline.",
        "",
        "Threshold definitions",
        "- eta_equal: smallest eta where mean(EQT) >= mean(BK).",
        "- eta_sig: smallest eta where CI_low(EQT) >= CI_high(BK).",
        f"- eta_equal: {format_eta_value(eta_equal)}",
        f"- eta_sig: {format_eta_value(eta_sig)}",
        "",
        "Run command (example)",
        "- python scripts/run_eta_threshold_batch.py --eta 0.087 --seed-start 0 --seed-end 30 --workers 20 --requests-per-seed 200 --resume",
        "",
        "Notes",
        "- BK is run once at bk_eta and reused across all etas during aggregation.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_threshold_report(
    path: Path,
    eta_equal: float | None,
    eta_sig: float | None,
    measured_eta: float,
    bk_measured: float | None,
    eqt_measured: float | None,
) -> None:
    lines = [
        "eta_threshold_report",
        f"eta_equal: {format_eta_value(eta_equal)}",
        f"eta_sig: {format_eta_value(eta_sig)}",
        f"measured_eta: {format_eta_value(measured_eta)}",
        f"BK_at_measured: {format_metric_value(bk_measured)}",
        f"EQT_at_measured: {format_metric_value(eqt_measured)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    etas = load_etas(args, config)
    bk_eta = resolve_bk_eta(args, config, etas)
    measured_eta = resolve_measured_eta(args, config, etas)
    baseline = resolve_baseline(args, config)
    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    derived_root = args.outdir / "derived"
    printed_header = [False]

    if not args.aggregate_only:
        attempted = 0
        skipped = 0
        succeeded = 0

        example_bk = build_sim_command(
            scenario="BK",
            eta=bk_eta,
            seed=args.seed_start,
            workers=args.workers,
            requests_per_seed=args.requests_per_seed,
            temp_dir=args.outdir / "tmp" / "BK" / f"eta_{format_eta(bk_eta)}" / f"seed_{args.seed_start}",
            baseline=baseline,
        )
        example_eqt = build_sim_command(
            scenario="EQT",
            eta=etas[0],
            seed=args.seed_start,
            workers=args.workers,
            requests_per_seed=args.requests_per_seed,
            temp_dir=args.outdir / "tmp" / "EQT" / f"eta_{format_eta(etas[0])}" / f"seed_{args.seed_start}",
            baseline=baseline,
        )
        print("Example BK command:", " ".join(example_bk))
        print("Example EQT command:", " ".join(example_eqt))

        for eta in etas:
            for scenario in scenarios:
                if scenario == "BK" and eta != bk_eta:
                    continue
                effective_eta = bk_eta if scenario == "BK" else eta
                eta_label = format_eta(effective_eta)
                for seed in iter_seeds(args.seed_start, args.seed_end):
                    derived_dir = derived_root / scenario / f"eta_{eta_label}" / f"seed_{seed}"
                    summary_csv = derived_dir / "summary.csv"
                    if args.resume and summary_csv.exists():
                        skipped += 1
                        continue

                    raw_dir = args.outdir / "raw" / scenario / f"eta_{eta_label}"
                    raw_dir.mkdir(parents=True, exist_ok=True)
                    raw_csv = raw_dir / f"seed_{seed}.csv"
                    raw_json = raw_dir / f"seed_{seed}.json"

                    if args.force or not raw_csv.exists():
                        temp_dir = args.outdir / "tmp" / scenario / f"eta_{eta_label}" / f"seed_{seed}"
                        run_simulation(
                            scenario=scenario,
                            eta=effective_eta,
                            seed=seed,
                            workers=args.workers,
                            requests_per_seed=args.requests_per_seed,
                            temp_dir=temp_dir,
                            baseline=baseline,
                        )
                        raw_source = temp_dir / "kbits_1.0" / "entanglement_service_raw.csv"
                        summary_source = temp_dir / "kbits_1.0" / "summary.json"
                        if not raw_source.exists():
                            raise FileNotFoundError(f"Missing raw CSV after run: {raw_source}")
                        shutil.copy2(raw_source, raw_csv)
                        if summary_source.exists():
                            shutil.copy2(summary_source, raw_json)
                        if not args.keep_temp and temp_dir.exists():
                            shutil.rmtree(temp_dir)

                    attempted += 1
                    requests_csv = derived_dir / "requests.csv"
                    normalize_raw(raw_csv, requests_csv, printed_header)
                    summarize_requests(requests_csv, derived_dir)
                    succeeded += 1

        total_summaries = len(list(derived_root.rglob("summary.csv")))
        print(
            f"Attempted: {attempted} | Skipped: {skipped} | Succeeded: {succeeded} | summaries: {total_summaries}"
        )

    results_path = aggregate_results(derived_root, args.outdir, args.artifacts_dir, etas, bk_eta)
    if results_path:
        agg = pd.read_csv(results_path)
        eta_equal, eta_sig = compute_thresholds(agg, etas)
        bk_measured = lookup_metric(agg, "BK", measured_eta, "mean_success_rate")
        eqt_measured = lookup_metric(agg, "EQT", measured_eta, "mean_success_rate")
        macros_path = args.artifacts_dir / "results_auto_eta_threshold.tex"
        write_macros(macros_path, measured_eta, bk_measured, eqt_measured, eta_equal, eta_sig)
        readme_path = args.artifacts_dir / "README_eta_threshold.md"
        write_readme(
            readme_path,
            etas,
            baseline,
            bk_eta,
            measured_eta,
            eta_equal,
            eta_sig,
            (args.seed_start, args.seed_end),
            args.requests_per_seed,
            args.workers,
        )
        report_path = args.artifacts_dir / "eta_threshold_report.txt"
        write_threshold_report(report_path, eta_equal, eta_sig, measured_eta, bk_measured, eqt_measured)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
