#!/usr/bin/env bash
set -euo pipefail

export OMP_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1

MODE=${MODE:-smoke} # smoke or prod
BASE_OUT=${BASE_OUT:-out/qn_paper}
RUN_NAME=${RUN_NAME:-$(date +%Y%m%d_%H%M%S)}

if [[ "${MODE}" == "smoke" ]]; then
  PRESET=${PRESET:-preset_non_saturated_smoke}
  REQUESTED_WORKERS=${WORKERS:-2}
else
  PRESET=${PRESET:-preset_hybrid_phase_default}
  REQUESTED_WORKERS=${WORKERS:-4}
fi

if [[ "${MODE}" != "smoke" && "${REQUESTED_WORKERS}" -lt 2 ]]; then
  echo "ERROR: WORKERS must be >=2 for non-smoke runs"
  exit 1
fi

EFFECTIVE_WORKERS=${REQUESTED_WORKERS}
if [[ "${EFFECTIVE_WORKERS}" -gt 4 ]]; then
  EFFECTIVE_WORKERS=4
fi
if [[ "${MODE}" == "smoke" && "${EFFECTIVE_WORKERS}" -lt 2 ]]; then
  EFFECTIVE_WORKERS=2
fi

OUT_DIR="${BASE_OUT}/${MODE}_${RUN_NAME}"
mkdir -p "${OUT_DIR}"

echo "Running phase sweep with PRESET=${PRESET} MODE=${MODE} WORKERS=${EFFECTIVE_WORKERS} OUT_DIR=${OUT_DIR}"

LINK_RATE_FLAGS=""
if [[ -n "${QT_RATE_IN:-}" ]]; then
  RATE_JSON="${OUT_DIR}/link_rates.json"
  python scripts/qn_build_link_rates_from_qt.py --in "${QT_RATE_IN}" --out-json "${RATE_JSON}"
  LINK_RATE_FLAGS="--link-rate-json ${RATE_JSON}"
fi

# Phase sweep
python scripts/qn_phase_sweep.py \
  --preset "${PRESET}" \
  --workers "${EFFECTIVE_WORKERS}" \
  --resume \
  --out-dir "${OUT_DIR}/phase"

python scripts/plot_qn_phase_sweep.py \
  --in-agg "${OUT_DIR}/phase/phase_agg.csv" \
  --out-dir "${OUT_DIR}/phase" \
  --title "Hybrid distance×eta phase (${MODE})"

# Crossover sensitivity (attn by default)
python scripts/qn_crossover_sensitivity.py \
  --preset preset_sensitivity_attn_default \
  --out-dir "${OUT_DIR}/sensitivity"

python scripts/plot_qn_crossover_sensitivity.py \
  --in-csv "${OUT_DIR}/sensitivity/crossover_sensitivity.csv" \
  --out-dir "${OUT_DIR}/sensitivity" \
  --title "Crossover sensitivity (${MODE})"

# Export summary table
python scripts/qn_export_summary_table.py \
  --phase "${OUT_DIR}/phase/phase_crossover.csv" \
  --sensitivity "${OUT_DIR}/sensitivity/crossover_sensitivity.csv" \
  --out-dir "${OUT_DIR}"

# Key-service run (smoke-level defaults for now)
python scripts/qn_key_service_availability.py \
  --preset preset_key_service_otp_smoke \
  --out-dir "${OUT_DIR}/key_service"

# Key-service sweep (paper figure)
python scripts/qn_key_service_sweep.py \
  --preset preset_key_service_otp_smoke \
  --workers "${EFFECTIVE_WORKERS}" \
  --resume \
  --out-dir "${OUT_DIR}/key_service_sweep" \
  ${LINK_RATE_FLAGS}

python scripts/plot_qn_key_service_sweep.py \
  --in-agg "${OUT_DIR}/key_service_sweep/key_service_sweep_agg.csv" \
  --out-dir "${OUT_DIR}/key_service_sweep" \
  --title "Key-service sweep (${MODE})"

# Migration frontier (paper figure)
python scripts/qn_key_service_migration_frontier.py \
  --preset preset_non_saturated_smoke \
  --workers "${EFFECTIVE_WORKERS}" \
  --resume \
  --out-dir "${OUT_DIR}/key_service_migration_frontier" \
  ${LINK_RATE_FLAGS}

for target in 0.9 0.99 0.999; do
  TARGET_DIR="${OUT_DIR}/key_service_migration_frontier/A${target}"
  mkdir -p "${TARGET_DIR}"
  python scripts/plot_qn_key_service_migration_frontier.py \
    --in-agg "${OUT_DIR}/key_service_migration_frontier/frontier_agg.csv" \
    --out-dir "${TARGET_DIR}" \
    --title "Migration frontier (${MODE})" \
    --targets "${target}"
done
