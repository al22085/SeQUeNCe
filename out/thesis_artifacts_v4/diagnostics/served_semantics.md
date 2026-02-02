# Served / success semantics (raw logs)

Raw columns in `entanglement_service_raw.csv`:
- `arrival_s`: request arrival time `t_arrival` (seconds).
- `deadline_s`: absolute deadline time (seconds). Set as `t_arrival + tau_s`.
- `served`: boolean; the simulator marks a request as served only if it is completed before its deadline.
- `t_done_s`: completion time when a request is served (seconds). Empty if not served.
- `bits_needed`: OTP bits required for this request.
- `bits_delivered`: delivered bits; equals `bits_needed` when served, otherwise 0.

Where these are written to CSV:
- `scripts/qn_entanglement_service_availability.py:165-176` defines raw headers, including `arrival_s`, `deadline_s`, `served`, `t_done_s`, `bits_needed`, `bits_delivered`.

Where `served` is set and deadline is checked:
- `sequence/qn/entanglement_service.py:212-222`
  - The deadline check is `t_now <= req.deadline` (line 218).
  - When satisfied, the simulator sets `req.served = True` and `req.t_done = t_now` (lines 220–221).

Implication:
- **`served` already implies deadline satisfied** because the code only sets `served=True` when `t_now <= deadline`.
- This is why `miss_deadline_rate_given_served` can be 0: misses are filtered out at the moment of service.
