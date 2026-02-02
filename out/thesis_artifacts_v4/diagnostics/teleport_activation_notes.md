# Teleport activation notes (Chapter 9 experiments)

Summary:
- **Teleportation protocol exists in SeQUeNCe** (e.g., `sequence/app/teleport_app.py`, `sequence/entanglement_management/teleportation.py`).
- **The Chapter 9 entanglement-service availability experiments do not invoke TeleportApp/TeleportProtocol.**
  The experiments use `scripts/qn_entanglement_service_availability.py` → `sequence/qn/entanglement_service.py`,
  which models entanglement generation and swapping on a fixed path, not application-level teleportation.

Evidence:
- `out/thesis_artifacts_v4/diagnostics/teleport_activation.csv` shows
  `n_requests_using_teleport = 0` and `teleport_edge_fraction = 0` for all seeds/scenarios.

Interpretation:
- **Teleportation did not “fire” in these experiments** because the availability simulator does not call
  teleportation protocols; it only uses entanglement generation + swapping to accumulate key bits.
- DQT≈EQT in some settings can occur because teleportation is not used; performance differences are driven by
  p_eg and other strategy parameters, not teleport application events.
