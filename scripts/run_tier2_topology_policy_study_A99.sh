#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_OUT_DIR="${OUT_DIR:-out}"
TOL_SWEEP_DIR="${BASE_OUT_DIR}/tier2_A099_pair_tolerance_sweep"

mkdir -p "${ROOT_DIR}/${BASE_OUT_DIR}"

python "${ROOT_DIR}/scripts/qn_stop_running_jobs.py"

# Ensure pinned TopologyBench zip exists under ./data/topologybench/
python "${ROOT_DIR}/scripts/qn_topologybench_fetch.py"

python "${ROOT_DIR}/scripts/qn_sweep_pair_tolerance.py" \
  --root-out-dir "${ROOT_DIR}/${TOL_SWEEP_DIR}" \
  --auto-select-topologies 5 \
  --targets-km 404,511,1002 \
  --pairs-per-target 2 \
  --tolerances 0.15,0.2,0.25,0.3,0.35 \
  --require-long-feasible

CHOSEN_TOL=$(
  python -c "import json; print(json.load(open('${ROOT_DIR}/${TOL_SWEEP_DIR}/chosen_tolerance.json'))['chosen_tolerance'])"
)
CHOSEN_TOPOS=$(
  python - <<PY
import json
data=json.load(open("${ROOT_DIR}/${TOL_SWEEP_DIR}/chosen_tolerance.json"))
print(",".join(data.get("chosen_topologies", [])))
PY
)
if [ -z "${CHOSEN_TOPOS}" ]; then
  echo "ERROR: No chosen_topologies found in ${TOL_SWEEP_DIR}/chosen_tolerance.json" >&2
  exit 1
fi
TOL_TAG=$(python -c "print(str('${CHOSEN_TOL}').replace('.', 'p'))")
OUT_DIR="${OUT_DIR:-${BASE_OUT_DIR}/tier2_A099_topology_policy_fullrange_k_5topos_tol${TOL_TAG}_feasible}"

python "${ROOT_DIR}/scripts/qn_run_topology_policy_upgrade_curves.py" \
  --topology-id-list "${CHOSEN_TOPOS}" \
  --upgrade-k-mode full_range \
  --upgrade-policies global_rank,pair_demand,pair_path_only \
  --eta 0.9 --target 0.99 --kbits 1.0 --seeds 0,1,2,3 \
  --targets-km 404,511,1002 --pairs-per-target 2 --pair-distance-rel-tol "${CHOSEN_TOL}" \
  --binary-search --load-min 0.001 --load-max 5.0 --load-tol 0.05 \
  --horizon-s 0.3 --tau-s 0.1 \
  --attempt-rate-opt-hz 5000 --attempt-rate-sc-hz 10000 \
  --coherence-opt-s 0.05 --coherence-sc-s 0.1 \
  --loss-db-per-km 0.2 --segment-length-km 50 \
  --swap-schedule balanced --network-scope shortest_path \
  --require-long-feasible \
  --workers 20 \
  --verify-parallel-mode pid_activity_strict \
  --preflight-task-seconds 3.0 --preflight-num-tasks 80 \
  --utilization-monitor-seconds 60 --utilization-monitor-samples 5 \
  --out-dir "${ROOT_DIR}/${OUT_DIR}"

cp "${ROOT_DIR}/${TOL_SWEEP_DIR}/tolerance_missing_summary.csv" "${ROOT_DIR}/${OUT_DIR}/tolerance_missing_summary.csv"
cp "${ROOT_DIR}/${TOL_SWEEP_DIR}/chosen_tolerance.json" "${ROOT_DIR}/${OUT_DIR}/chosen_tolerance.json"

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
  --analysis-dir "${ROOT_DIR}/${OUT_DIR}/analysis_path_coverage" \
  --out-path "${ROOT_DIR}/${OUT_DIR}/plots_linearity/tier2_key_findings.md"

echo "Tier2 A=0.99 study complete: ${OUT_DIR}"
