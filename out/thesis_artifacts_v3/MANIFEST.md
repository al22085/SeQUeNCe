# Thesis artifacts v3 manifest

This pack targets professor concerns (1)-(7) from the request. Paths are relative to `/home/al22085/workspace/SeQUeNCe/`.

## Reproducibility (1)
- `out/thesis_artifacts_v3/config/run_config.json` — machine‑readable snapshot of concrete parameters for every experiment in this pack (etas, strategies, seeds, arrival intervals, tau_s, bits, knobs, etc.).

## Eta affects physical parameters (2)
- `out/thesis_artifacts_v3/diagnostics/eta_codepath.md` — codepath evidence linking eta → p_eg.
- `out/thesis_artifacts_v3/diagnostics/eta_to_peg.csv` — table of eta → p_eg for BK/DQT/EQT.
- `out/thesis_artifacts_v3/figures/fig_eta_to_peg.pdf` (+`.png`) — plot of eta → p_eg.
- `out/thesis_artifacts_v3/results/results_eta_threshold.csv` — eta sweep success rates.
- `out/thesis_artifacts_v3/figures/fig_eta_threshold_curve.pdf` (+`.png`) — BK vs EQT success vs eta with 95% CI.

## Deadline matters (3)
- `out/thesis_artifacts_v3/results/results_deadline_sweep.csv` — success vs tau_s sweep.
- `out/thesis_artifacts_v3/figures/fig_deadline_sweep_curve.pdf` (+`.png`) — success vs tau_s + mean slack where available.

## Offered load explains low success (4)
- `out/thesis_artifacts_v3/results/results_load_sweep.csv` — success vs arrival interval (offered load).
- `out/thesis_artifacts_v3/figures/fig_load_sweep_curve.pdf` (+`.png`) — success vs arrival interval plot.

## Upgrade‑k has no effect (5)
- `out/thesis_artifacts_v3/diagnostics/upgrade_k_usage.csv` — per‑seed activation/path coverage metrics.
- `out/thesis_artifacts_v3/figures/fig_upgrade_k_activation.pdf` (+`.png`) — activation fraction + path‑upgraded fraction vs k.
- `out/thesis_artifacts_v3/diagnostics/upgrade_k_activation_attempt.md` — stress run attempt + overlap analysis.
- `out/thesis_artifacts_v3/diagnostics/upgrade_k_stress/kbits_1.0/entanglement_service_raw.csv` — raw stress run output.
- `out/thesis_artifacts_v3/diagnostics/upgrade_k_stress/kbits_1.0/summary.json` — stress run summary.

## Normalized topology sweep (6)
- `out/thesis_artifacts_v3/diagnostics/topology_normalization.md` — tau_s normalization formula & distances.
- `out/thesis_artifacts_v3/results/results_topology_normalized.csv` — normalized topology results.
- `out/thesis_artifacts_v3/figures/fig_topology_normalized_bar.pdf` (+`.png`) — normalized topology comparison plot.

## Full extensions vs upstream diff (7)
- `out/thesis_artifacts_v3/docs/sequence_extensions_full.md` — BASE/HEAD commits, full name‑status list, layer summary, and diff snippets.

## Baseline snapshot (supporting)
- `out/thesis_artifacts_v3/results/results_baseline.csv` — BK/DQT/EQT baseline at eta=0.03.
- `out/thesis_artifacts_v3/figures/fig_baseline_bar_eta003.pdf` (+`.png`) — baseline comparison figure.
