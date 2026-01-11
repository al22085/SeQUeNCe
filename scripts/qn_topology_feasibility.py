"""Feasibility utilities for representative-distance pair selection."""

from __future__ import annotations

from typing import Dict, List, Tuple

from scripts.qn_topologies import build_topology_from_dist_map


def dijkstra(topo: Dict[str, List[str]], dist: Dict[tuple, float], src: str) -> Dict[str, float]:
    import heapq

    pq = [(0.0, src)]
    best = {src: 0.0}
    while pq:
        d, n = heapq.heappop(pq)
        if d > best[n]:
            continue
        for nei in topo[n]:
            key = tuple(sorted((n, nei)))
            w = dist[key]
            nd = d + w
            if nei not in best or nd < best[nei]:
                best[nei] = nd
                heapq.heappush(pq, (nd, nei))
    return best


def all_pairs_sp_km(dist_map: Dict[tuple, float]) -> List[Tuple[float, str, str]]:
    topo = build_topology_from_dist_map(dist_map)
    nodes = sorted(topo.keys())
    pairs: List[Tuple[float, str, str]] = []
    for i in range(len(nodes)):
        src = nodes[i]
        best = dijkstra(topo, dist_map, src)
        for j in range(i + 1, len(nodes)):
            dst = nodes[j]
            if dst not in best:
                continue
            pairs.append((best[dst] / 1000.0, src, dst))
    return pairs


def within_tol(sp_km: float, target_km: float, abs_tol: float, rel_tol: float) -> bool:
    abs_err = abs(sp_km - target_km)
    if abs_tol and abs_err <= abs_tol:
        return True
    if rel_tol and target_km > 0:
        return abs_err / target_km <= rel_tol
    return False


def label_for_target(idx: int, target: float) -> str:
    labels = ["short", "medium", "long"]
    if idx < len(labels):
        return labels[idx]
    return f"target_{target}"


def compute_target_feasibility(
    dist_map: Dict[tuple, float],
    targets_km: List[float],
    pairs_per_target: int,
    abs_tol: float,
    rel_tol: float,
    *,
    pairs: List[Tuple[float, str, str]] | None = None,
) -> Dict[str, object]:
    if pairs is None:
        pairs = all_pairs_sp_km(dist_map)
    total_expected = pairs_per_target * len(targets_km)
    missing_by_label: Dict[str, int] = {}
    counts_by_label: Dict[str, int] = {}
    best_error_by_label: Dict[str, float] = {}

    total_missing = 0
    for idx, target in enumerate(targets_km):
        label = label_for_target(idx, target)
        count = 0
        best_err = None
        for sp_km, _, _ in pairs:
            err = abs(sp_km - target)
            if best_err is None or err < best_err:
                best_err = err
            if within_tol(sp_km, target, abs_tol, rel_tol):
                count += 1
        counts_by_label[label] = count
        best_error_by_label[label] = best_err if best_err is not None else float("nan")
        missing = max(0, pairs_per_target - count)
        missing_by_label[label] = missing
        total_missing += missing

    completeness = (total_expected - total_missing) / total_expected if total_expected else 0.0
    missing_long = missing_by_label.get("long", 0)

    return {
        "missing_by_label": missing_by_label,
        "counts_by_label": counts_by_label,
        "best_error_by_label": best_error_by_label,
        "total_missing": total_missing,
        "total_expected": total_expected,
        "completeness": completeness,
        "missing_long": missing_long,
        "feasible_all_targets": total_missing == 0,
    }


def filter_candidates_by_feasibility(
    candidates: List[Dict[str, object]],
    require_long_feasible: bool,
    require_target_feasible: bool,
) -> List[Dict[str, object]]:
    filtered = []
    for row in candidates:
        missing_long = int(row.get("missing_long", 0))
        missing_total = int(row.get("missing_total", 0))
        if require_long_feasible and missing_long > 0:
            continue
        if require_target_feasible and missing_total > 0:
            continue
        filtered.append(row)
    if not filtered:
        return []

    # sort by missing_total (asc), completeness (desc), diameter_km (asc), topology_id
    def key(r: Dict[str, object]) -> tuple:
        return (
            int(r.get("missing_total", 0)),
            -float(r.get("completeness", 0.0)),
            float(r.get("diameter_km", 0.0)),
            str(r.get("topology_id", "")),
        )

    return sorted(filtered, key=key)
