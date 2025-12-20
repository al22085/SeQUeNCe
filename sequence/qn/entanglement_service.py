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
    extra_latency_s: float = 0.0


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
    swap_schedule: str = "sequential",
    debug_stats: bool = False,
) -> Dict:
    """Simulate request-level availability on a given path."""
    rng = np.random.default_rng(seed)
    edges = [tuple(sorted((path[i], path[i + 1]))) for i in range(len(path) - 1)]

    # Generate request arrivals
    requests: List[Request] = []
    if num_requests is None and lambda_req is None:
        num_requests = 10
    total_bits_requested = 0.0
    if lambda_req is None:
        # spread over horizon
        for i in range(num_requests):
            t_arr = (i / max(1, num_requests)) * horizon_s
            deadline = t_arr + tau_s
            bits_needed = otp_data_rate_bps * otp_session_duration_s * otp_directions
            requests.append(Request(t_arrival=t_arr, deadline=deadline, bits_needed=bits_needed))
            total_bits_requested += bits_needed
    else:
        t = 0.0
        while t < horizon_s:
            t += _sample_exp(rng, lambda_req)
            if t > horizon_s:
                break
            deadline = t + tau_s
            bits_needed = otp_data_rate_bps * otp_session_duration_s * otp_directions
            requests.append(Request(t_arrival=t, deadline=deadline, bits_needed=bits_needed))
            total_bits_requested += bits_needed

    event_heap: List[Tuple[float, str, object]] = []
    stats = {
        "eg_success_events": 0,
        "swap_attempts": 0,
        "swap_success": 0,
        "swap_fail": 0,
        "mem_expired_events": 0,
        "swap_levels": 0,
        "num_segments": len(edges),
    }

    # schedule initial entanglement successes using Poisson thinning:
    # attempts ~ Poisson(R), success prob p_eg => successes ~ Poisson(R*p_eg) (exact).
    for e in edges:
        edge = edge_params[e]
        rate_succ = edge.attempt_rate_hz * edge.p_eg
        if rate_succ <= 0:
            continue
        t = _sample_exp(rng, rate_succ)
        if t <= horizon_s + tau_s:
            heapq.heappush(event_heap, (t, "eg_success", e))

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
        if swap_schedule == "balanced":
            # Require one available pair on every edge before starting balanced swaps.
            ready_pairs: List[Tuple[float, str, str]] = []
            for e in edges:
                while edge_pairs[e] and edge_pairs[e][0] <= t_now:
                    edge_pairs[e].pop(0)
                    stats["mem_expired_events"] += 1
                if not edge_pairs[e]:
                    return
                exp = edge_pairs[e].pop(0)
                ready_pairs.append((exp, e[0], e[1]))

            # perform level-by-level disjoint swaps
            current_time = t_now + swap_params.latency_s
            pairs = ready_pairs
            level = 0
            while len(pairs) > 1:
                level += 1
                stats["swap_levels"] += 1
                next_pairs: List[Tuple[float, str, str]] = []
                i = 0
                while i + 1 < len(pairs):
                    stats["swap_attempts"] += 1
                    exp_left, u_left, v_left = pairs[i]
                    exp_right, u_right, v_right = pairs[i + 1]
                    if exp_left <= current_time or exp_right <= current_time:
                        stats["mem_expired_events"] += 1
                        i += 2
                        continue
                    if rng.random() < swap_params.p_bsm:
                        stats["swap_success"] += 1
                        exp_new = min(exp_left, exp_right)
                        next_pairs.append((exp_new, u_left, v_right))
                    else:
                        stats["swap_fail"] += 1
                    i += 2
                if i < len(pairs):
                    next_pairs.append(pairs[i])
                pairs = next_pairs
                current_time += swap_params.latency_s
                if not pairs:
                    break

            if pairs:
                if debug_stats and len(edges) > 1 and stats["swap_attempts"] == 0:
                    raise AssertionError("balanced swap produced end-to-end pair without swap attempts")
                ab_pairs += 1
                key_bits_available += key_bits_per_pair
                serve_pending(current_time)
        else:
            # sequential existing behavior
            while all(edge_pairs[e] for e in edges):
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
                success = True
                for _ in range(len(edges) - 1):
                    stats["swap_attempts"] += 1
                    if rng.random() >= swap_params.p_bsm:
                        stats["swap_fail"] += 1
                        success = False
                        break
                    stats["swap_success"] += 1
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
        if kind == "eg_success":
            edge = payload
            params = edge_params[edge]
            stats["eg_success_events"] += 1
            rate_succ = params.attempt_rate_hz * params.p_eg
            if rate_succ > 0:
                next_t = now + _sample_exp(rng, rate_succ)
                if next_t <= horizon_s + tau_s:
                    heapq.heappush(event_heap, (next_t, "eg_success", edge))
            available_t = now + params.extra_latency_s
            edge_pairs[edge].append(available_t + params.coherence_time_s)
            edge_pairs[edge].sort()
            try_swap(available_t + swap_params.latency_s)
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
        "bits_requested": total_bits_requested,
        "bits_delivered": sum(r.bits_delivered for r in requests),
        "debug_stats": stats if debug_stats else None,
    }
