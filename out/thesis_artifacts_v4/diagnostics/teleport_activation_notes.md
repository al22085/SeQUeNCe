# Teleport activation notes (EQT runs)

Observed result:
- In the Chapter 9 entanglement‑service availability runs, **teleport activation is 0**.
- `teleport_activation.csv` reports `n_requests_with_teleport = 0` and `teleport_request_fraction = 0` for all seeds/scenarios.
- Path‑edge inspection also yields `path_edges_teleport = 0` (no teleport edges in the chosen path).

Why teleportation does not fire here:
- These experiments use `scripts/qn_entanglement_service_availability.py` → `sequence/qn/entanglement_service.py`,
  which models entanglement generation + swapping on a fixed shortest path, not TeleportApp/TeleportProtocol.
- As a result, **EQT does not invoke teleportation in this pipeline**; its effects are via strategy parameters (eta → p_eg).

Why DQT≈EQT can still occur:
- Because teleportation is not exercised, performance differences are driven by p_eg scaling and other strategy knobs,
  and can saturate or be masked by low offered load / tight deadline regimes.
