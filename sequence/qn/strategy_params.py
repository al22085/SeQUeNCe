"""Strategy parameter mapping for entanglement service (BK/DQT/EQT)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple


@dataclass
class StrategyKnobs:
    attempt_rate_opt_hz: float = 1e5
    attempt_rate_sc_hz: float = 1e5
    p_bsm_opt: float = 0.9
    p_bsm_sc: float = 0.95
    coherence_opt_s: float = 0.02
    coherence_sc_s: float = 0.03
    loss_db_per_km: float = 0.2
    p_eg_per_km: float | None = None
    transduction_latency_s: float = 0.0
    swap_latency_s: float = 0.0
    p_eg_floor: float = 1e-6


def loss_to_prob(dist_km: float, loss_db_per_km: float | None, p_eg_per_km: float | None) -> float:
    if p_eg_per_km is not None:
        return max(0.0, p_eg_per_km ** dist_km)
    if loss_db_per_km is None:
        return 1.0
    attn_db = dist_km * loss_db_per_km
    return math.exp(-attn_db * math.log(10) / 10.0)


def edge_params_for_strategy(
    strategy: str, dist_km: float, eta: float, knobs: StrategyKnobs
) -> Tuple[float, float, float, float, float]:
    """Return (p_eg, attempt_rate_hz, coherence_time_s, p_bsm, extra_latency_s)."""
    base_prob = loss_to_prob(dist_km, knobs.loss_db_per_km, knobs.p_eg_per_km)
    if strategy == "EQT":
        p_eg = max(knobs.p_eg_floor, base_prob * eta * eta)
        attempt_rate = knobs.attempt_rate_sc_hz
        coherence = knobs.coherence_sc_s
        p_bsm = knobs.p_bsm_sc
        latency = knobs.transduction_latency_s
    elif strategy == "DQT":
        p_eg = max(knobs.p_eg_floor, base_prob * eta)
        attempt_rate = knobs.attempt_rate_sc_hz
        coherence = knobs.coherence_sc_s
        p_bsm = knobs.p_bsm_sc
        latency = knobs.transduction_latency_s
    else:  # BK / optical baseline
        p_eg = max(knobs.p_eg_floor, base_prob)
        attempt_rate = knobs.attempt_rate_opt_hz
        coherence = knobs.coherence_opt_s
        p_bsm = knobs.p_bsm_opt
        latency = 0.0
    return p_eg, attempt_rate, coherence, p_bsm, latency


def swap_params_for_strategy(strategy: str, knobs: StrategyKnobs) -> Tuple[float, float]:
    p_bsm = knobs.p_bsm_sc if strategy in ("DQT", "EQT") else knobs.p_bsm_opt
    return p_bsm, knobs.swap_latency_s
