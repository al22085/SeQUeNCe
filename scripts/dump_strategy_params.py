#!/usr/bin/env python3
"""Dump strategy parameter mapping for EQT across eta values."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy, loss_to_prob


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dump EQT p_eg values across eta.")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("scripts/eta_threshold_config.json"),
        help="JSON config with eta sweep list.",
    )
    parser.add_argument(
        "--distance-km",
        type=float,
        default=50.0,
        help="Representative edge distance in km.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("out/paper_artifacts/dump_strategy_params.csv"),
        help="Output CSV path.",
    )
    return parser.parse_args()


def load_etas(config: Path) -> list[float]:
    if not config.exists():
        raise FileNotFoundError(f"Config not found: {config}")
    payload = json.loads(config.read_text(encoding="utf-8"))
    etas = payload.get("etas", [])
    if not etas:
        raise ValueError("No etas found in config.")
    return [float(x) for x in etas]


def main() -> int:
    args = parse_args()
    etas = load_etas(args.config)
    knobs = StrategyKnobs()
    base_prob = loss_to_prob(args.distance_km, knobs.loss_db_per_km, knobs.p_eg_per_km)

    rows = []
    for eta in etas:
        p_eg_raw = base_prob * eta * eta
        p_eg_used, _, _, _, _ = edge_params_for_strategy("EQT", args.distance_km, eta, knobs)
        is_clamped = p_eg_used <= knobs.p_eg_floor + 1e-12
        rows.append(
            {
                "eta": eta,
                "distance_km": args.distance_km,
                "loss_db_per_km": knobs.loss_db_per_km,
                "base_prob": base_prob,
                "p_eg_raw": p_eg_raw,
                "p_eg_floor": knobs.p_eg_floor,
                "p_eg_used": p_eg_used,
                "is_clamped": is_clamped,
            }
        )

    df = pd.DataFrame(rows)
    df.to_csv(args.out, index=False)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
