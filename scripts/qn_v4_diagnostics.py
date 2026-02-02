#!/usr/bin/env python3
"""Generate v4 diagnostics: route switching usage + teleport activation summary."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_topologies import load_distance_dataset, subdivide_edges, shortest_path_edges


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build v4 diagnostics for switching + teleport activation.")
    p.add_argument(
        "--config",
        type=Path,
        default=Path("out/thesis_artifacts_v4/config/run_config.json"),
        help="Path to run_config.json copied into v4.",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("out/thesis_artifacts_v4/diagnostics"),
        help="Output directory for diagnostics CSVs.",
    )
    p.add_argument(
        "--route-seeds",
        type=str,
        default="0,1,2",
        help="Comma list of seeds for route switching usage CSV.",
    )
    return p.parse_args()


def parse_list(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def route_switch_usage(config: dict, out_dir: Path, seeds: Iterable[int]) -> Path:
    baseline = config.get("experiments", {}).get("baseline", {})
    eta = baseline.get("etas", [None])[0]
    src = str(baseline.get("src_node", "12"))
    dst = str(baseline.get("dst_node", "13"))
    distance_dataset_id = baseline.get("distance_dataset_id", "sndlib_great_circle_heuristic")
    segment_length_km = config.get("defaults", {}).get("segment_length_km", 50.0)

    dist_map = load_distance_dataset(distance_dataset_id)
    expanded_edges, _, _ = subdivide_edges(dist_map, segment_length_km=segment_length_km)

    rows = []
    for seed in seeds:
        # deterministic shortest path search
        path_edges = shortest_path_edges(expanded_edges, src, dst)
        route_search_attempts = 1
        fallback_triggered = 0 if path_edges else 1
        rows.append(
            {
                "seed": seed,
                "scenario": "BK",
                "eta": eta,
                "route_search_attempts": route_search_attempts,
                "fallback_triggered": fallback_triggered,
            }
        )

    out_path = out_dir / "route_switch_usage.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seed",
                "scenario",
                "eta",
                "route_search_attempts",
                "fallback_triggered",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    return out_path


def iter_raw_logs() -> Iterable[tuple[str, Path]]:
    # BK/EQT baseline (eta=0.03) from study_upgrade_k raw (k=0)
    base = Path("out/thesis_artifacts/study_upgrade_k/raw")
    for scenario in ("BK", "EQT"):
        root = base / scenario / "eta_0.03" / "k_0"
        if not root.exists():
            continue
        for raw_path in sorted(root.glob("seed_*/kbits_1.0/entanglement_service_raw.csv")):
            yield scenario, raw_path

    # DQT baseline from study_transducer_availability raw
    dqt_root = Path("out/thesis_artifacts/study_transducer_availability/raw/nsfnet/DQT/eta_0.03000")
    if dqt_root.exists():
        for raw_path in sorted(dqt_root.glob("seed_*/entanglement_service_raw.csv")):
            yield "DQT", raw_path


def teleport_activation(config: dict, out_dir: Path) -> Path:
    baseline = config.get("experiments", {}).get("baseline", {})
    eta = baseline.get("etas", [None])[0]
    src = str(baseline.get("src_node", "12"))
    dst = str(baseline.get("dst_node", "13"))
    distance_dataset_id = baseline.get("distance_dataset_id", "sndlib_great_circle_heuristic")
    segment_length_km = config.get("defaults", {}).get("segment_length_km", 50.0)

    # Path introspection (no teleport edges defined in this model)
    dist_map = load_distance_dataset(distance_dataset_id)
    expanded_edges, _, _ = subdivide_edges(dist_map, segment_length_km=segment_length_km)
    path_edges = shortest_path_edges(expanded_edges, src, dst)
    path_edge_total = len(path_edges)
    teleport_edges = set()  # no teleport edges defined in qn_entanglement_service
    teleport_on_path = 0
    if path_edges:
        for *_, orig in path_edges:
            if orig in teleport_edges:
                teleport_on_path += 1
    teleport_edge_fraction = (teleport_on_path / path_edge_total) if path_edge_total else 0.0
    n_paths_with_teleport_edge = 1 if teleport_on_path > 0 else 0

    rows = []
    for scenario, raw_path in iter_raw_logs():
        seed = int(raw_path.parent.parent.name.split("_")[1]) if "kbits_1.0" in raw_path.parts else int(raw_path.parent.name.split("_")[1])
        n_requests = 0
        n_served = 0
        n_success = 0
        with raw_path.open() as f:
            reader = csv.DictReader(f)
            for row in reader:
                n_requests += 1
                served = str(row.get("served", "")).lower() in ("1", "true", "t", "yes")
                if served:
                    n_served += 1
                t_done_raw = row.get("t_done_s", "")
                t_done = float(t_done_raw) if str(t_done_raw).strip() not in ("", "None") else None
                deadline = float(row["deadline_s"])
                if served and t_done is not None and t_done <= deadline:
                    n_success += 1
        rows.append(
            {
                "seed": seed,
                "scenario": scenario,
                "eta": eta,
                "n_requests": n_requests,
                "n_served": n_served,
                "n_success": n_success,
                "n_requests_using_teleport": 0,
                "teleport_request_fraction": 0.0,
                "n_paths_with_teleport_edge": n_paths_with_teleport_edge,
                "teleport_edge_fraction": teleport_edge_fraction,
            }
        )

    out_path = out_dir / "teleport_activation.csv"
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "seed",
                "scenario",
                "eta",
                "n_requests",
                "n_served",
                "n_success",
                "n_requests_using_teleport",
                "teleport_request_fraction",
                "n_paths_with_teleport_edge",
                "teleport_edge_fraction",
            ],
        )
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda r: (r["scenario"], r["seed"])))
    return out_path


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    args.out_dir.mkdir(parents=True, exist_ok=True)

    route_switch_usage(cfg, args.out_dir, parse_list(args.route_seeds))
    teleport_activation(cfg, args.out_dir)


if __name__ == "__main__":
    main()
