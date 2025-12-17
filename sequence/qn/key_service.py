from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np


@dataclass
class RequestLog:
    t_arrival: float
    t_start: float
    served: bool
    wait: float
    src: str
    dst: str
    hops: int
    bits: float
    path: List[Tuple[str, str]]


def compute_link_key_rate(strategy: str, link_attrs: Dict, strategy_params: Dict, base_key_rate_bps: float) -> float:
    multiplier = strategy_params.get("multiplier", 1.0)
    strat_mult = strategy_params.get(strategy.lower() + "_multiplier", 1.0)
    return base_key_rate_bps * multiplier * strat_mult


def simulate_key_service(
    topology: Dict[str, List[str]],
    *,
    strategy: str,
    seed: int,
    horizon_s: float,
    lambda_req: float,
    tau_s: float,
    crypto_model: str,
    otp_data_rate_bps: float,
    otp_session_duration_s: float,
    session_key_bits: int,
    kmax_bits: float,
    base_key_rate_bps: float,
    strategy_params: Dict,
    routing: str = "shortest",
    allow_wait: bool = True,
    reserve_mode: str = "upfront",
    link_rates: Dict[Tuple[str, str], float] | None = None,
    otp_directions: int = 2,
) -> Dict:
    assert routing == "shortest"
    assert reserve_mode == "upfront"
    assert otp_directions in (1, 2)
    rng = np.random.default_rng(seed)

    # shortest paths via BFS (unweighted)
    def shortest_path(src, dst):
        from collections import deque

        q = deque([[src]])
        visited = {src}
        while q:
            path = q.popleft()
            node = path[-1]
            if node == dst:
                return path
            for nei in topology[node]:
                if nei not in visited:
                    visited.add(nei)
                    q.append(path + [nei])
        return None

    # link pools
    links = {}
    for a, neighs in topology.items():
        for b in neighs:
            if (b, a) in links:
                continue
            if link_rates and (a, b) in link_rates:
                rate = link_rates[(a, b)]
            elif link_rates and (b, a) in link_rates:
                rate = link_rates[(b, a)]
            else:
                rate = compute_link_key_rate(strategy, {}, strategy_params, base_key_rate_bps)
            links[(a, b)] = {"rate": rate, "last": 0.0, "k": kmax_bits / 2}
            links[(b, a)] = links[(a, b)]

    def update_pool(link, now):
        info = links[link]
        dt = now - info["last"]
        if dt > 0:
            info["k"] = min(kmax_bits, info["k"] + info["rate"] * dt)
            info["last"] = now

    t = 0.0
    logs: List[RequestLog] = []
    served = 0
    total = 0
    waits = []
    hops_list = []
    path_choices = []
    block_count = 0

    while t < horizon_s:
        ia = rng.exponential(1.0 / lambda_req) if lambda_req > 0 else horizon_s
        t_arrival = t + ia
        if t_arrival > horizon_s:
            break
        t = t_arrival
        # pick src/dst
        nodes = list(topology.keys())
        src = nodes[rng.integers(0, len(nodes))]
        dst = src
        while dst == src:
            dst = nodes[rng.integers(0, len(nodes))]

        # demand
        if crypto_model == "otp":
            duration = otp_session_duration_s
            bits = otp_data_rate_bps * duration * otp_directions
        else:
            bits = session_key_bits

        path_nodes = shortest_path(src, dst)
        if not path_nodes or len(path_nodes) < 2:
            continue
        path_links = [(path_nodes[i], path_nodes[i + 1]) for i in range(len(path_nodes) - 1)]

        waits_per_link = []
        for e in path_links:
            update_pool(e, t_arrival)
            info = links[e]
            if info["rate"] <= 0:
                wait = math.inf
            elif info["k"] >= bits:
                wait = 0.0
            else:
                wait = (bits - info["k"]) / info["rate"]
            waits_per_link.append(wait)
        wait_req = max(waits_per_link)
        t_start = t_arrival + wait_req
        served_flag = wait_req <= tau_s
        if served_flag:
            for e in path_links:
                update_pool(e, t_start)
                links[e]["k"] -= bits
            served += 1
            waits.append(wait_req)
            hops_list.append(len(path_links))
            path_choices.append(path_links)
        else:
            block_count += 1

        total += 1
        logs.append(
            RequestLog(
                t_arrival=t_arrival,
                t_start=t_start if served_flag else math.nan,
                served=served_flag,
                wait=wait_req if wait_req != math.inf else math.inf,
                src=src,
                dst=dst,
                hops=len(path_links),
                bits=bits,
                path=path_links,
            )
        )

    availability = served / total if total else 0.0
    mean_wait = float(np.mean(waits)) if waits else None
    mean_hops = float(np.mean(hops_list)) if hops_list else None
    return {
        "availability": availability,
        "block_prob": 1 - availability,
        "served": served,
        "total": total,
        "mean_wait": mean_wait,
        "mean_hops": mean_hops,
        "strategy": strategy,
        "seed": seed,
        "logs": logs,
    }
