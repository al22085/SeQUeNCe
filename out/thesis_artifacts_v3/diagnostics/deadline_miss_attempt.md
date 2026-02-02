# Deadline miss attempt

Attempted to induce deadline misses by tightening tau_s and increasing load.

Parameters:
- topology: nsfnet
- strategy: BK
- eta: 0.03
- src=12, dst=13
- num_requests: 200
- horizon_s: 0.05 (arrival_interval_s=0.00025)
- tau_s: 0.01
- seed: 0

Raw log: /home/al22085/workspace/SeQUeNCe/out/thesis_artifacts_v3/diagnostics/deadline_miss_attempt_run/kbits_1.0/entanglement_service_raw.csv

Observed counts:
- total requests: 200
- served: 0
- misses among served (t_done > deadline): 0

Result: miss_deadline_rate_given_served remains 0 because the simulator only marks a request served when t_now <= deadline (see sequence/qn/entanglement_service.py:218).