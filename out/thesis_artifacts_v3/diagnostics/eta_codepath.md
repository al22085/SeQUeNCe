# η -> p_eg code path (entanglement service model)

This note traces how η affects the entanglement-generation success probability p_eg in the **entanglement service** simulator used by the thesis runs.

## Code path (entry → p_eg → event probability)
1. **CLI entry**: `scripts/qn_entanglement_service_availability.py`
   - Parses `--eta` and builds `StrategyKnobs`.
   - For each path edge, calls:
     `edge_params_for_strategy(chosen_strategy, dist_km, eta, knobs)`.
   - `chosen_strategy` is `BK` unless (a) requested strategy is `BK`, or (b) the edge is upgraded (EQT_UPGRADE path uses EQT only on upgraded edges).

2. **Strategy mapping**: `sequence/qn/strategy_params.py`
   - `loss_to_prob(dist_km, loss_db_per_km, p_eg_per_km)` computes **base_prob** from distance.
   - `edge_params_for_strategy(...)` converts (strategy, dist_km, η) into p_eg:
     - **BK**: `p_eg = max(p_eg_floor, base_prob)`
     - **DQT**: `p_eg = max(p_eg_floor, base_prob * η)`
     - **EQT**: `p_eg = max(p_eg_floor, base_prob * η^2)`

3. **Event probability usage**: `sequence/qn/entanglement_service.py`
   - Uses p_eg to generate entanglement success events via a Poisson process:
     `rate_succ = attempt_rate_hz * p_eg`.
   - Each edge gets an independent success process at that rate; events schedule entanglement availability on that edge.

## Scope note
This trace is **only** for the entanglement-service abstraction used in thesis experiments (EG + swapping with retries). It does **not** invoke the low-level QT hardware models (e.g., `sequence/entanglement_management/generation/qt_eqt.py`).
