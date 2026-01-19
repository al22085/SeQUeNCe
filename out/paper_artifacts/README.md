# Paper Artifacts

Metric
- Availability = deadline-based request success rate.
- success = (served == 1) AND (t_done_s <= deadline_s).

Raw to requests.csv mapping
- t_start = arrival_s
- deadline = deadline_s
- t_finish = t_done_s (success only)

Eta usage
- eta passed via --eta to scripts/qn_entanglement_service_availability.py.
- eta used in sequence/qn/strategy_params.py (edge_params_for_strategy) to compute p_eg.

Parameter matrix
- study_transducer_availability: BK/DQT/EQT, eta=0.6/0.8/0.9, seeds=30, requests/seed=200, workers=20.
- study_eta_sanity: DQT/EQT, eta=0.05/0.95, seeds=10, requests/seed=200, workers=20.
- study_eta_threshold: BK/EQT, eta=1e-5..0.8 (see scripts/eta_threshold_config.json), seeds=30, requests/seed=200, workers=20.
- study_upgrade_k: BK/DQT/EQT (k=0) + EQT_UPGRADE (k=1,2,4,8), eta=0.6/0.8/0.9, seeds=30, requests/seed=200, workers=20.
- study_topology_sweep: BK/EQT/EQT_UPGRADE (best k@eta=0.8), eta=0.8, seeds=30, requests/seed=200, workers=20.

Commands
- Batch runner: scripts/run_upgrade_k_batch.py (eta=0.6/0.8/0.9, seeds 0-30, workers=20).
- Batch runner: scripts/run_topology_batch.py (eta=0.8, seeds 0-30, workers=20).
- Batch runner: scripts/run_eta_threshold_batch.py (eta sweep, seeds 0-30, workers=20).
- Availability: scripts/compute_availability.py.
- Consolidation: scripts/build_paper_artifacts.py.
- Plots: scripts/plot_paper_artifacts.py.
- Plot: scripts/plot_eta_threshold.py.
- Strategy params: scripts/dump_strategy_params.py (writes out/paper_artifacts/dump_strategy_params.csv).

Topology sweep
- topologies: NSFNET13, TOP_0_SANET, TOP_103_GEANT.

Raw data
- upgrade-k raw archive: out/study_upgrade_k_raw.tar.gz
- transducer availability raw CSVs: out/study_transducer_availability/raw
- eta sanity raw CSVs: out/study_eta_sanity/raw
- eta threshold raw CSVs: out/study_eta_threshold/raw
- topology sweep raw CSVs: out/study_topology_sweep/raw

Git commit: 703e7caef96a04061b2d6efe48d7d9ff4c7a734d

Key findings
- eta=0.8 BK mean=0.0000 (95% CI 0.0000--0.0000).
- eta=0.8 best EQT_UPGRADE k=1 mean=0.0000 (95% CI 0.0000--0.0000). (best among upgrade-k; may not improve over EQT)
- eta* criterion: smallest eta with EQT mean >= BK mean and ci95_low_EQT >= ci95_high_BK; if none, fall back to mean-only.
- eta threshold sweep (BK vs EQT, nsfnet): all mean success rates are 0.0 for eta=1e-5..0.8, so no meaningful eta*; fig2_eta_threshold marks the first eta with EQT>=BK but CIs overlap at 0 throughout.
- strategy param dump (out/paper_artifacts/dump_strategy_params.csv): EQT p_eg is clamped to p_eg_floor for eta<=0.003 at 50 km, but availability remains 0 even when p_eg scales above the floor, indicating another bottleneck.
