"""Discrete-event entanglement service simulator (EG + memory + swapping + retries)."""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

import numpy as np


@dataclass
class EdgeParams:
    attempt_rate_hz: float
    p_eg: float
    coherence_time_s: float


@dataclass
class SwapParams:
    p_bsm: float
    latency_s: float = 0.0


@dataclass
class Request:
    t_arrival: float
    deadline: float
    bits_needed: float
    served: bool = False
    t_done: Optional[float] = None
    bits_delivered: float = 0.0


def _sample_exp(rng: np.random.Generator, rate: float) -> float:
    if rate <= 0:
        return math.inf
    return rng.exponential(1.0 / rate)


def simulate_entanglement_service(
    path: List[str],
    edge_params: Dict[Tuple[str, str], EdgeParams],
    swap_params: SwapParams,
    *,
    seed: int,
    horizon_s: float,
    tau_s: float,
    num_requests: Optional[int] = None,
    lambda_req: Optional[float] = None,
    otp_data_rate_bps: float = 1e3,
    otp_session_duration_s: float = 0.01,
    otp_directions: int = 2,
    key_bits_per_pair: float = 1.0,
    targets=(0.9, 0.99, 0.999),
) -> Dict:
    """Simulate request-level availability on a given path."""
    rng = np.random.default_rng(seed)
    edges = [tuple(sorted((path[i], path[i + 1]))) for i in range(len(path) - 1)]

    # Generate request arrivals
    requests: List[Request] = []
    if num_requests is None and lambda_req is None:
        num_requests = 10
    if lambda_req is None:
        # spread over horizon
        for i in range(num_requests):
            t_arr = (i / max(1, num_requests)) * horizon_s
            deadline = t_arr + tau_s
            bits_needed = otp_data_rate_bps * otp_session_duration_s * otp_directions
            requests.append(Request(t_arrival=t_arr, deadline=deadline, bits_needed=bits_needed))
    else:
        t = 0.0
        while t < horizon_s:
            t += _sample_exp(rng, lambda_req)
            if t > horizon_s:
                break
            deadline = t + tau_s
            bits_needed = otp_data_rate_bps * otp_session_duration_s * otp_directions
            requests.append(Request(t_arrival=t, deadline=deadline, bits_needed=bits_needed))

    event_heap: List[Tuple[float, str, object]] = []

    # schedule initial EG attempts
    for e in edges:
        edge = edge_params[e]
        t = _sample_exp(rng, edge.attempt_rate_hz)
        heapq.heappush(event_heap, (t, "eg_attempt", e))

    # schedule request arrivals
    for req in requests:
        heapq.heappush(event_heap, (req.t_arrival, "req", req))

    # per-edge entangled pair expiry times
    edge_pairs: Dict[Tuple[str, str], List[float]] = {e: [] for e in edges}

    key_bits_available = 0.0
    pending: List[Request] = []
    ab_pairs = 0
    now = 0.0

    def clean_expired(t_now: float):
        for e in edges:
            ep = edge_params[e]
            edge_pairs[e] = [exp for exp in edge_pairs[e] if exp > t_now and exp - t_now <= ep.coherence_time_s + 1e-12]

    def try_swap(t_now: float):
        nonlocal key_bits_available, ab_pairs
        # remove expired pairs first
        clean_expired(t_now)
        # need at least one pair per edge
        while all(edge_pairs[e] for e in edges):
            # take one per edge
            pairs = []
            ok = True
            for e in edges:
                exp = edge_pairs[e].pop(0)
                if exp <= t_now:
                    ok = False
                    break
                pairs.append((e, exp))
            if not ok:
                continue
            # perform swaps sequentially along path
            success = True
            for _ in range(len(edges) - 1):
                if rng.random() >= swap_params.p_bsm:
                    success = False
                    break
            if success:
                ab_pairs += 1
                key_bits_available += key_bits_per_pair
                serve_pending(t_now)

    def serve_pending(t_now: float):
        nonlocal key_bits_available
        pending.sort(key=lambda r: r.t_arrival)
        for req in pending:
            if req.served:
                continue
            if key_bits_available >= req.bits_needed and t_now <= req.deadline:
                key_bits_available -= req.bits_needed
                req.served = True
                req.t_done = t_now
                req.bits_delivered = req.bits_needed

    while event_heap:
        t, kind, payload = heapq.heappop(event_heap)
        now = t
        if now > horizon_s + tau_s:
            break
        if kind == "eg_attempt":
            edge = payload
            params = edge_params[edge]
            # schedule next attempt
            next_t = now + _sample_exp(rng, params.attempt_rate_hz)
            heapq.heappush(event_heap, (next_t, "eg_attempt", edge))
            if rng.random() < params.p_eg:
                edge_pairs[edge].append(now + params.coherence_time_s)
                edge_pairs[edge].sort()
                try_swap(now + swap_params.latency_s)
        elif kind == "req":
            req = payload
            pending.append(req)
            serve_pending(now)

    served = sum(1 for r in requests if r.served)
    total = len(requests)
    availability = served / total if total else 0.0
    waits = [max(0.0, (r.t_done or r.deadline) - r.t_arrival) for r in requests if r.served]
    mean_wait = float(np.mean(waits)) if waits else 0.0
    target_eval = {tgt: availability >= tgt for tgt in targets}
    return {
        "availability": availability,
        "served": served,
        "total": total,
        "mean_wait": mean_wait,
        "ab_pairs": ab_pairs,
        "requests": requests,
        "targets": target_eval,
    }
