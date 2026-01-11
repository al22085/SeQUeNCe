# Tier2 Research Summary (A=0.99, research-only)

## Overview
This repository contains a research-only Tier2 pipeline that produces CSV/plots and a neutral markdown summary; it does not generate TeX or bundle artifacts.

## Objective
Quantify request-level availability at SLA target A=0.99 across multiple topologies and upgrade policies using representative distances (404/511/1002 km).

## Method
- Topology inputs: TopologyBench datasets imported into repo-local CSVs, then auto-selected for feasibility.
- Pair selection: shortest-path distances on original graphs; targets 404/511/1002 km; pairs_per_target=2; rel_tol=0.15.
- Simulation: balanced swapping, shortest_path scope, loss_db_per_km=0.2, eta=0.9, kbits=1.0.
- Upgrade policies: global_rank, pair_demand, pair_path_only; full-range upgrade_k per topology (0..|E|).

## Experimental setup
- Output directory: `out/tier2_A099_researchonly_5topos`
- Selected topologies (from summary_upgrade_curves.csv): TOP_11_TATANID, TOP_52_CONUS100, TOP_59_PALMETTO, TOP_64_JGN2PLUS, TOP_68_EON
- Chosen tolerance: 0.15

## Outputs (research-only)
- summary_upgrade_curves.csv
- line_vs_curve_summary.csv
- analysis_path_coverage/path_coverage_thresholds_summary.csv
- plots_linearity/ (PNG plots)
- analysis_path_coverage/ (CSV + plots)
- plots_linearity/tier2_key_findings.md (neutral markdown summary)

## Verification strategy
- Strict parallel preflight + utilization monitoring (ProcessPool).
- Chunked pytest groups documented in README and docs/RESEARCH_ONLY_AUDIT.md (full pytest -q may exceed 120s).

## Results (from computed outputs)
- Preflight workers: requested=20, effective=20, active=20
- Preflight CPU: aggregate_cpu=2006.6666666666665, expected_cpu=2000.0
- Missing pairs total (summary_upgrade_curves.csv): 0 (labels={})

### Linearity metrics by policy (line_vs_curve_summary.csv)
- global_rank: fraction_nonlinear=1.0 median_r2=0.6068406831224665 median_curvature=0.029079502022781 worst_curvature=0.228237482950103
- pair_demand: fraction_nonlinear=1.0 median_r2=0.2998227150206591 median_curvature=0.0260000582517808 worst_curvature=0.228237482950103
- pair_path_only: fraction_nonlinear=1.0 median_r2=0.1204775925183198 median_curvature=0.0210597935670011 worst_curvature=0.2155576227862084

### Path coverage thresholds by policy (path_coverage_thresholds_summary.csv)
- global_rank: coverage_threshold_k_median=14.5 k_star_median=0.5
- pair_demand: coverage_threshold_k_median=3.0 k_star_median=0.5
- pair_path_only: coverage_threshold_k_median=1.0 k_star_median=0.5