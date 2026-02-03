# Baseline condition provenance (Appendix A)

Appendix A’s request‑log example corresponds to the **baseline comparison** experiment used in Chapter 9 / Table 7.1.

Baseline parameters (from `out/thesis_artifacts_v4/docs/ch9_baseline_params.txt`):
- eta = 0.03
- tau_s = 5.0 seconds (deadline window)
- src = 12, dst = 13 (fixed pair)
- arrival_interval_s = 0.0005 seconds
- requests_per_seed = 200
- seeds = 0–29
- horizon_s = 0.1 seconds
- strategies compared: BK, DQT, EQT

Slack definition (units: seconds):
- **slack = deadline - t_finish**, where `deadline` and `t_finish` are the per‑request times recorded in the log.

Why Appendix A uses tau=5.0:
- The appendix log is taken from the **baseline comparison row in Table 7.1**, which uses tau_s = 5.0; the example is aligned to that baseline condition.
