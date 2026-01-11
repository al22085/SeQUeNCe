# Tier2 Diff Rationale (since baseline-upstream-ok)

## A. Executive summary
This document explains every tracked change since baseline commit `5600eb79` and ties them to the Tier2 (A=0.99) research-only pipeline (CSV/plots/neutral markdown outputs only). It reconstructs the pipeline, its verification layers (strict parallel preflight + utilization monitoring), representative pair selection with tolerance/feasibility handling, and analysis outputs (line-vs-curve + path coverage). No TeX/zip tooling is part of the final OSS state.

## B. Research objective & experimental design
Tier2 focuses on request-level availability at SLA target A=0.99 using representative shortest-path distances (404/511/1002 km), full-range upgrade-k curves (k=0..|E|), and upgrade policies (global_rank, pair_demand, pair_path_only). The pipeline uses balanced swapping, shortest-path scope, fixed loss_db_per_km, and deterministic seeds.

## C. Milestones (derived from commit history)
- **QT transduction protocols + availability metrics**: qt-transduction + availability utilities + line sweep scripts.
- **Network-level availability benchmarks**: line topology + reservation-based E2E availability.
- **Key-service and entanglement-service simulators**: OTP/session availability + discrete-event EG/swap model.
- **TopologyBench data pipeline + selection**: pinned fetcher, importers, pair selection, feasibility filtering.
- **Parallel preflight + utilization monitoring**: ProcessPool verification, CPU limit detection, stop-jobs helper.
- **Tier2 A=0.99 runner + tolerance sweep**: representative distances + full-range upgrade-k curves.
- **Analysis layer**: linearity + path-coverage metrics + plotting helpers.
- **Research-only audit docs**: tracked-only audits + chunked pytest recipe.
- **TeX/zip tooling removal (net-zero in final diff)**: temporary TeX/zip/bundle utilities were removed; final tracked state contains no TeX/zip consumption tooling.

## D. Pipeline architecture
Key components:
- Data import + topology selection + representative pair selection
- Simulation drivers (entanglement-service, key-service, network availability)
- Strict parallel preflight and utilization monitoring
- Analysis: curve linearity and path coverage; plotting helpers

## E. Verification & reproducibility
Strict parallel verification prevents single-core runs; stop-jobs helper avoids overlapping processes. Chunked pytest is the official verification path due to 120s timeouts for full test runs.

## F. Representative-pair selection & missing data
Tolerance sweep and feasibility-first selection ensure representative pairs exist for each target; missing pairs are explicitly tracked when they occur.

## G. Analysis layer
Linearity metrics (R^2, curvature) and path coverage thresholds characterize whether upgrade-k curves are linear or nonlinear across topologies and policies.

## H. File-by-file diff rationale table

| Path | Status | Purpose | Why needed for research | Interfaces/Outputs | Related milestone |
|---|---|---|---|---|---|
| `.gitignore` | M | Ignore generated artifacts (out/, logs) | Keep repo clean for research runs | Git ignore rules | repo-hygiene |
| `CHANGELOG.md` | M | Update top-level documentation | Document research-only workflow and verification | Markdown docs | docs-audit |
| `README.md` | M | Update top-level documentation | Document research-only workflow and verification | Markdown docs | docs-audit |
| `data/nsfnet_distances.csv` | A | Topology/dataset inputs and manifest | Provide pinned, deterministic inputs | CSV/JSON datasets | data-pipeline |
| `data/nsfnet_distances.md` | A | Topology/dataset inputs and manifest | Provide pinned, deterministic inputs | CSV/JSON datasets | data-pipeline |
| `data/topologybench_manifest.json` | A | Topology/dataset inputs and manifest | Provide pinned, deterministic inputs | CSV/JSON datasets | data-pipeline |
| `docs/RESEARCH_ONLY_AUDIT.md` | A | Research-only audit / methodology docs | Provide reproducible verification path | Markdown docs | docs-audit |
| `example/bb84_two_edge_cli.py` | A | Example scripts for protocols | Demonstrate usage / regression coverage | CLI example | examples |
| `example/quantum_transduction/direct_conversion.py` | M | Example scripts for protocols | Demonstrate usage / regression coverage | CLI example | examples |
| `example/quantum_transduction/entanglement_swapping.py` | M | Example scripts for protocols | Demonstrate usage / regression coverage | CLI example | examples |
| `pyproject.toml` | M | Adjust project deps/test config | Support new tooling/tests | Packaging/test config | infra |
| `requirements.txt` | M | Adjust project deps/test config | Support new tooling/tests | Packaging/test config | infra |
| `scripts/plot_qn_crossover_sensitivity.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_curve_linearity_report.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_deadline_factor_calibrate.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_entanglement_service_frontier.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_entanglement_service_nsfnet.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_entanglement_service_robustness.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_key_service_migration_frontier.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_key_service_sweep.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_network_sweep.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_path_coverage_mechanism.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_phase_sweep.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_policy_comparison.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_topology_policy_sensitivity.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qn_upgrade_threshold_mechanism.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/plot_qt_line_sweep.py` | A | Plotting helper for analysis outputs | Visualize CSV results | PNG/PDF plots under out/ | analysis-plots |
| `scripts/qn_analyze_path_coverage_across_topologies.py` | A | Analysis/export helper | Summarize curves/coverage/policies | CSV/plots under out/ | analysis-plots |
| `scripts/qn_analyze_upgrade_threshold.py` | A | Analysis/export helper | Summarize curves/coverage/policies | CSV/plots under out/ | analysis-plots |
| `scripts/qn_build_link_rates_from_qt.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_crossover_sensitivity.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_deadline_factor_calibrate.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_dump_path_params.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_e2e_proof_minimal.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_entanglement_service_availability.py` | A | Discrete-event entanglement-service runner | Model request-level availability with EG+swap | CSV/plots under out/ | entanglement-service |
| `scripts/qn_entanglement_service_calibrate_pair.py` | A | Discrete-event entanglement-service runner | Model request-level availability with EG+swap | CSV/plots under out/ | entanglement-service |
| `scripts/qn_entanglement_service_frontier.py` | A | Discrete-event entanglement-service runner | Model request-level availability with EG+swap | CSV/plots under out/ | entanglement-service |
| `scripts/qn_entanglement_service_param_scan.py` | A | Discrete-event entanglement-service runner | Model request-level availability with EG+swap | CSV/plots under out/ | entanglement-service |
| `scripts/qn_entanglement_service_robustness_frontier.py` | A | Discrete-event entanglement-service runner | Model request-level availability with EG+swap | CSV/plots under out/ | entanglement-service |
| `scripts/qn_entanglement_service_sweep.py` | A | Discrete-event entanglement-service runner | Model request-level availability with EG+swap | CSV/plots under out/ | entanglement-service |
| `scripts/qn_experiment_presets.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_export_curve_linearity_report.py` | A | Analysis/export helper | Summarize curves/coverage/policies | CSV/plots under out/ | analysis-plots |
| `scripts/qn_export_frontier_key_numbers.py` | A | Analysis/export helper | Summarize curves/coverage/policies | CSV/plots under out/ | analysis-plots |
| `scripts/qn_export_summary_table.py` | A | Analysis/export helper | Summarize curves/coverage/policies | CSV/plots under out/ | analysis-plots |
| `scripts/qn_export_upgrade_k_curve.py` | A | Analysis/export helper | Summarize curves/coverage/policies | CSV/plots under out/ | analysis-plots |
| `scripts/qn_generate_tier2_key_findings.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_import_distances_from_topologybench_generic.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_import_nsfnet_distances_from_topologybench.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_key_service_availability.py` | A | Key-service (OTP/session) simulator | Model key-pool availability | CSV/plots under out/ | key-service |
| `scripts/qn_key_service_migration_frontier.py` | A | Key-service (OTP/session) simulator | Model key-pool availability | CSV/plots under out/ | key-service |
| `scripts/qn_key_service_sweep.py` | A | Key-service (OTP/session) simulator | Model key-pool availability | CSV/plots under out/ | key-service |
| `scripts/qn_list_topologybench.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_longpair_counters_vs_k.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_network_availability.py` | A | Network-level availability benchmark | Request-level E2E availability on line/NSFNET | CSV/plots under out/ | network-availability |
| `scripts/qn_network_availability_sequence.py` | A | Network-level availability benchmark | Request-level E2E availability on line/NSFNET | CSV/plots under out/ | network-availability |
| `scripts/qn_network_baseline_table.py` | A | Network-level availability benchmark | Request-level E2E availability on line/NSFNET | CSV/plots under out/ | network-availability |
| `scripts/qn_network_sweep.py` | A | Network-level availability benchmark | Request-level E2E availability on line/NSFNET | CSV/plots under out/ | network-availability |
| `scripts/qn_phase_sweep.py` | A | Phase/eta sweep tooling | Study availability vs eta/distance | CSV/plots under out/ | phase-sweeps |
| `scripts/qn_run_policy_comparison.py` | A | Analysis/export helper | Summarize curves/coverage/policies | CSV/plots under out/ | analysis-plots |
| `scripts/qn_run_topology_and_policy_sensitivity.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_run_topology_policy_upgrade_curves.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_select_diverse_topologies.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_select_nsfnet_pairs.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_select_pairs_by_sp_distance.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_select_topology_pairs.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_stop_running_jobs.py` | A | Parallel preflight/monitor utilities | Ensure real multiprocessing before runs | parallel_report.json | parallel-verification |
| `scripts/qn_sweep_pair_tolerance.py` | A | Research runner/util | Support Tier2 pipeline | CSV/plots under out/ | tier2-pipeline |
| `scripts/qn_topologies.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_topology_feasibility.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_topologybench_fetch.py` | A | Topology data import/selection utilities | Deterministic topology inputs and pairs | CSV/JSON outputs under out/ | topology-selection |
| `scripts/qn_validate_chain_against_phase.py` | A | Phase/eta sweep tooling | Study availability vs eta/distance | CSV/plots under out/ | phase-sweeps |
| `scripts/qt_dq_bk_table.py` | A | QT transduction experiment script | Benchmark BK/DQT/EQT behaviors | CSV/plots in out/ | qt-transduction |
| `scripts/qt_line_availability.py` | A | QT transduction experiment script | Benchmark BK/DQT/EQT behaviors | CSV/plots in out/ | qt-transduction |
| `scripts/qt_line_eta_sweep.py` | A | QT transduction experiment script | Benchmark BK/DQT/EQT behaviors | CSV/plots in out/ | qt-transduction |
| `scripts/qt_line_sweep.py` | A | QT transduction experiment script | Benchmark BK/DQT/EQT behaviors | CSV/plots in out/ | qt-transduction |
| `scripts/run_qn_common_factor_and_sweep_smoke.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `scripts/run_qn_deadline_calibrate_smoke.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `scripts/run_qn_figures.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `scripts/run_qn_network_sweep_prod.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `scripts/run_qn_phase_prod.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `scripts/run_qt_eta_sweep_compare_prod.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `scripts/run_qt_eta_sweep_prod.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `scripts/run_qt_sweep_prod.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `scripts/run_tier2_topology_policy_study_A99.sh` | A | Reproducible shell runners | Automate experiments | Shell script; writes out/ | runners |
| `sequence/app/benchmark_request_app.py` | A | Repository change | Research pipeline evolution | N/A | misc |
| `sequence/components/memory.py` | M | Component updates for QT/transduction | Hardware modeling support | Component behavior | qt-transduction |
| `sequence/components/transducer.py` | M | Component updates for QT/transduction | Hardware modeling support | Component behavior | qt-transduction |
| `sequence/components/transmon.py` | M | Component updates for QT/transduction | Hardware modeling support | Component behavior | qt-transduction |
| `sequence/constants.py` | M | Repository change | Research pipeline evolution | N/A | misc |
| `sequence/entanglement_management/generation/qt_dq.py` | A | QT entanglement generation protocol | Enable BK/DQT/EQT strategies | Protocol classes | qt-transduction |
| `sequence/entanglement_management/generation/qt_eqt.py` | A | QT entanglement generation protocol | Enable BK/DQT/EQT strategies | Protocol classes | qt-transduction |
| `sequence/qn/entanglement_service.py` | A | Core entanglement-service simulator | Faithful EG+swap request model | Python API | entanglement-service |
| `sequence/qn/key_service.py` | A | Key-service simulator core | OTP/session availability model | Python API | key-service |
| `sequence/qn/parallel.py` | A | Strict parallel verification + monitoring | Prevent single-core runs | parallel_report.json | parallel-verification |
| `sequence/qn/strategy_params.py` | A | BK/DQT/EQT parameter mapping | Expose physics knobs consistently | Python API | strategy-params |
| `sequence/qn/topologybench_fetch.py` | A | Pinned TopologyBench fetcher | Deterministic dataset import | data/topologybench/real_topologies.zip | data-pipeline |
| `sequence/transduction/__init__.py` | A | Transduction layer implementation | Model QT conversion | Module classes | qt-transduction |
| `sequence/transduction/qt_layer0.py` | A | Transduction layer implementation | Model QT conversion | Module classes | qt-transduction |
| `sequence/utils/availability.py` | A | Shared availability metric helper | Consistent availability definition | Utility API | metrics |
| `tests/components/test_transmon_transducer_integration.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/entanglement_management/test_dqt_eta_param.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/entanglement_management/test_generation.py` | M | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/entanglement_management/test_generation_qt_dq.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/entanglement_management/test_generation_qt_eqt.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/entanglement_management/test_generation_qt_network_strategy.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_analyze_path_coverage_across_topologies_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_build_link_rates_from_qt.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_e2e_proof_minimal.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_balanced_invariants.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_balanced_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_determinism.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_frontier_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_kbits.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_long_chain_sanity.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_robustness_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_entanglement_service_sweep_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_export_curve_linearity_report_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_generate_tier2_key_findings_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_import_topologybench.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_key_service_determinism.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_key_service_frontier_monotonic.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_key_service_frontier_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_key_service_monotonic.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_key_service_resume.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_key_service_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_key_service_sweep_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_network_availability_line4_debug.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_network_availability_sequence_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_network_availability_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_parallel_verify.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_phase_sweep_resume_parallel_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_policy_comparison_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_presets_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_run_topology_policy_upgrade_curves_auto_select_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_run_topology_policy_upgrade_curves_insufficient.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_run_topology_policy_upgrade_curves_no_node_filter.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_run_topology_policy_upgrade_curves_preflight_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_run_topology_policy_upgrade_curves_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_select_pairs_by_sp_distance.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_select_pairs_by_sp_distance_missing.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_stop_running_jobs.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_strategy_params.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_sweep_pair_tolerance_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_tier2_pipeline_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_topologies_distances.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_topology_feasibility_selection.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_topology_policy_sensitivity_smoke.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_topologybench_fetch.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_topologybench_generic_import_list_select.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_upgrade_path_coverage.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/network/test_qn_upgrade_policy_pair_demand.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/qkd/test_bb84_two_edge_cli.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |
| `tests/utils/test_availability.py` | A | Automated test coverage for new tooling | Verification of research pipeline | pytest | tests |

## I. Current state checklist
- Run Tier2: `scripts/run_tier2_topology_policy_study_A99.sh` (research-only).
- Verify outputs: `summary_upgrade_curves.csv`, `line_vs_curve_summary.csv`, `path_coverage_thresholds_summary.csv`, `parallel_report.json`.
- Run chunked pytest per README/RESEARCH_ONLY_AUDIT.md.

## J. Appendix: command outputs used (short excerpts)
The following commands were used to build this report:
- `git log --oneline --decorate --reverse 5600eb79..HEAD`
- `git diff --name-status 5600eb79..HEAD`
- `git diff 5600eb79..HEAD -- <path>` (per-file inspection)
- `git ls-files | rg -n "\.tex\b|\.zip\b|paper_artifacts|latex_include|ZipSlip|SHA256SUMS"`
- `git ls-files | rg -n "\bpaper\b"`
- `find out -maxdepth 4 -type f -name "summary_upgrade_curves.csv" -o -name "line_vs_curve_summary.csv" -o -name "path_coverage_thresholds_summary.csv" -o -name "parallel_report.json" -o -name "tier2_key_findings.md"`

### Computed outputs used (if present)
- Preflight: requested_workers=20, effective_workers=20, active_workers=20, aggregate_cpu=2006.6666666666665, expected_cpu=2000.0
- Missing pairs total: 0, labels={}
- Topologies (from summary_upgrade_curves.csv): TOP_11_TATANID, TOP_52_CONUS100, TOP_59_PALMETTO, TOP_64_JGN2PLUS, TOP_68_EON
- Chosen tolerance: 0.15
- Linearity policy global_rank: fraction_nonlinear=1.0, median_r2=0.6068406831224665, median_curvature=0.029079502022781, worst_curvature=0.228237482950103
- Linearity policy pair_demand: fraction_nonlinear=1.0, median_r2=0.2998227150206591, median_curvature=0.0260000582517808, worst_curvature=0.228237482950103
- Linearity policy pair_path_only: fraction_nonlinear=1.0, median_r2=0.1204775925183198, median_curvature=0.0210597935670011, worst_curvature=0.2155576227862084
- Coverage policy global_rank: coverage_threshold_k_median=14.5, k_star_median=0.5
- Coverage policy pair_demand: coverage_threshold_k_median=3.0, k_star_median=0.5
- Coverage policy pair_path_only: coverage_threshold_k_median=1.0, k_star_median=0.5
