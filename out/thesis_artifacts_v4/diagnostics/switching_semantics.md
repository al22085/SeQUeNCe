# Switching / route re-search semantics

Scope: qn entanglement-service availability experiments (Chapter 9 artifacts).

## What exists
- **Single shortest-path selection** per seed, using `shortest_path_edges(...)`.
  - `scripts/qn_entanglement_service_availability.py:185-187`
- **Per-edge parameter selection** for upgrades (EQT on selected edges, BK otherwise).
  - `scripts/qn_entanglement_service_availability.py:190-193`
- **Endpoint fallback only** if user-specified nodes are not in the expanded graph.
  - `scripts/qn_entanglement_service_availability.py:138-146`

## What does NOT exist (in this experiment path)
- **Route re-search on allocation failure**: there is no loop that retries with alternate paths.
- **Fallback to alternative routes**: no k-shortest / multipath / reroute logic is used.
- **Dynamic BK↔EQT strategy switching**: strategy selection is static per run; upgrades only apply to preselected edges (no runtime switching).

## How to phrase in thesis
- “**Path switching is not implemented in the entanglement-service availability experiments**; we select a single shortest path once per request pair. The only fallback is to default endpoints if an invalid node is specified. Dynamic strategy switching (BK↔EQT) is future work.”

## Quantitative evidence (diagnostic)
- `out/thesis_artifacts_v4/diagnostics/route_switch_usage.csv`
  - For baseline seeds 0–2, `route_search_attempts = 1` and `fallback_triggered = 0`, consistent with a single shortest-path selection and no rerouting.
