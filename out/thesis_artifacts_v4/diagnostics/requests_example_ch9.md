# Chapter 9 request log snippet (baseline)

Source (absolute path):
- /home/al22085/workspace/SeQUeNCe/out/thesis_artifacts/study_transducer_availability/derived/nsfnet/DQT/eta_0.03000/seed_0/requests.csv

Scenario: DQT
Seed: 0

Baseline context (from run_config.json):
- eta = 0.03
- arrival_interval_s = 0.0005
- tau_s (deadline window) = 5.0
- requests_per_seed = 200
- horizon_s = 0.1
- src=12, dst=13

Definitions:
- slack = deadline - t_finish (for success rows)
- success = (served == True) AND (t_done <= deadline)
  (served/t_done are already encoded as success in the derived requests.csv)

The file `requests_example_ch9.csv` contains the first 15 rows (including header)
so the appendix log aligns with the Chapter 9 time scale and slack discussion.
