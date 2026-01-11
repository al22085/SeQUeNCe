#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${OUT_DIR:-out/tier2_A099_topology_policy_fullrange_k_5topos}"

python "${ROOT_DIR}/scripts/qn_stop_running_jobs.py"

# Ensure pinned TopologyBench zip exists under ./data/topologybench/
python "${ROOT_DIR}/scripts/qn_topologybench_fetch.py"

python "${ROOT_DIR}/scripts/qn_run_topology_policy_upgrade_curves.py" \
  --auto-select-topologies 5 \
  --upgrade-k-mode full_range \
  --upgrade-policies global_rank,pair_demand,pair_path_only \
  --eta 0.9 --target 0.99 --kbits 1.0 --seeds 0,1,2,3 \
  --targets-km 404,511,1002 --pairs-per-target 2 --pair-distance-rel-tol 0.15 \
  --binary-search --load-min 0.001 --load-max 5.0 --load-tol 0.05 \
  --horizon-s 0.3 --tau-s 0.1 \
  --attempt-rate-opt-hz 5000 --attempt-rate-sc-hz 10000 \
  --coherence-opt-s 0.05 --coherence-sc-s 0.1 \
  --loss-db-per-km 0.2 --segment-length-km 50 \
  --swap-schedule balanced --network-scope shortest_path \
  --workers 20 \
  --verify-parallel-mode pid_activity_strict \
  --preflight-task-seconds 3.0 --preflight-num-tasks 80 \
  --utilization-monitor-seconds 60 --utilization-monitor-samples 5 \
  --out-dir "${ROOT_DIR}/${OUT_DIR}"

python "${ROOT_DIR}/scripts/qn_export_curve_linearity_report.py" \
  --root-dir "${ROOT_DIR}/${OUT_DIR}" \
  --workers 2

python "${ROOT_DIR}/scripts/plot_qn_curve_linearity_report.py" \
  --root-dir "${ROOT_DIR}/${OUT_DIR}" \
  --workers 2

python "${ROOT_DIR}/scripts/qn_analyze_path_coverage_across_topologies.py" \
  --root-dir "${ROOT_DIR}/${OUT_DIR}" \
  --out-dir "${ROOT_DIR}/${OUT_DIR}/analysis_path_coverage" \
  --workers 2

python "${ROOT_DIR}/scripts/plot_qn_path_coverage_mechanism.py" \
  --analysis-dir "${ROOT_DIR}/${OUT_DIR}/analysis_path_coverage" \
  --workers 2

python "${ROOT_DIR}/scripts/qn_generate_paper_key_findings.py" \
  --root-dir "${ROOT_DIR}/${OUT_DIR}" \
  --analysis-dir "${ROOT_DIR}/${OUT_DIR}/analysis_path_coverage"

echo "Tier2 A=0.99 study complete: ${OUT_DIR}"
