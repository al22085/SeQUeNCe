# Deadline vs served/success

Observation from results_deadline_sweep.csv:
- miss_deadline_rate_given_served is 0 across all tau_s values.
- served_rate and mean_success_rate still increase with larger tau_s (deadline window).

Examples:
- BK: tau_s=0.1 -> served_rate=0.000000, mean_success_rate=0.000000; tau_s=10.0 -> served_rate=0.046333, mean_success_rate=0.046333
- EQT: tau_s=0.1 -> served_rate=0.000000, mean_success_rate=0.000000; tau_s=10.0 -> served_rate=0.068333, mean_success_rate=0.068333

Why miss|served = 0:
- In the simulator, a request is only marked served when the service completion time t_now is <= deadline (sequence/qn/entanglement_service.py:218).
- This makes missed deadlines impossible *conditional on served*, so the deadline affects availability by gating which requests become served in the first place.