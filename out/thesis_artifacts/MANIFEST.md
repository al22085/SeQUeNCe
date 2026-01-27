# Thesis artifacts manifest

This pack consolidates all deadline-based availability studies and diagnostics under `out/thesis_artifacts`.

## Figures
- `out/thesis_artifacts/figures/fig_eta_threshold_curve.pdf/png` → Thesis Fig. T1
  - Conclusion: BK vs EQT availability is nearly flat across eta (0.01–0.80); no clear threshold in this range, indicating eta-insensitivity/saturation.
- `out/thesis_artifacts/figures/fig_baseline_bar_eta003.pdf/png` → Thesis Fig. T2
  - Conclusion: At eta=0.03, DQT/EQT slightly exceed BK in availability but all remain low; baseline comparison for representative eta.
- `out/thesis_artifacts/figures/fig_upgrade_k_curve.pdf/png` → Thesis Fig. T3
  - Conclusion: With baseline-matched config at eta=0.03, EQT_UPGRADE (k=1,2,4,8) matches EQT and does not exceed it; BK remains lower.
- `out/thesis_artifacts/figures/fig_topology_bar.pdf/png` → Thesis Fig. T4
  - Conclusion: Across NSFNET13 / TOP_0_SANET / TOP_103_GEANT at eta=0.03, BK vs EQT differences are not observable; availability saturated near 0.
- `out/thesis_artifacts/figures/fig_bottleneck_diagnosis.pdf/png` → Thesis Fig. T5
  - Conclusion: Served-rate and timing diagnostics are largely constant vs eta, explaining eta-insensitivity via bottlenecks/saturation.

## Tables / CSVs
- `out/thesis_artifacts/results/results_master.csv` → Thesis Table T0 (master consolidated results)
- `out/thesis_artifacts/results/results_eta_threshold.csv` → Thesis Table T1 (eta-threshold sweep BK vs EQT)
- `out/thesis_artifacts/results/results_baseline.csv` → Thesis Table T2 (BK/DQT/EQT baseline at eta=0.03)
- `out/thesis_artifacts/results/results_upgrade_k.csv` → Thesis Table T3 (upgrade-k study at eta=0.03)
- `out/thesis_artifacts/results/results_topology.csv` → Thesis Table T4 (topology sweep at eta=0.03)

## Diagnostics
- `out/thesis_artifacts/diagnostics/eta_diagnosis.csv` → Supports Fig. T5 (eta sweep diagnostics)
- `out/thesis_artifacts/diagnostics/baseline_diagnosis.csv` → Supports Fig. T2/T5 (baseline diagnostics)
- `out/thesis_artifacts/diagnostics/diagnosis_summary.txt` → Short narrative snippet for eta-insensitivity
- `out/thesis_artifacts/diagnostics/consistency_report.txt` → Baseline vs upgrade-k config comparison (eta=0.03)
- `out/thesis_artifacts/diagnostics/consistency_check.txt` → Automated assertion output (baseline vs upgrade-k rates)

## Config / Provenance
- `out/thesis_artifacts/config/run_config.json` → Parameter snapshot (seeds, requests, eta list, k list, workers, timing)
- `out/thesis_artifacts/sequence_extensions.md` → Summary of code extensions vs upstream and rationale

## Git transfer
- `out/thesis_artifacts/bundles/thesis_artifacts_<shortsha>.bundle` → Git bundle for offline transfer (created in Step F)
