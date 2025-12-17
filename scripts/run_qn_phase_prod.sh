#!/usr/bin/env bash
set -euo pipefail

MODE=${MODE:-full} # full or smoke
OUT_DIR=${1:-out/qn_phase_${MODE}}

if [[ "${MODE}" == "smoke" ]]; then
  DISTANCES=${DISTANCES:-"1000,2000"}
  ETAS=${ETAS:-"0.6,0.8,1.0"}
  SEEDS=${SEEDS:-"0,1"}
  NUM_TRIALS=${NUM_TRIALS:-10}
else
  DISTANCES=${DISTANCES:-"500,1000,2000,5000"}
  ETAS=${ETAS:-"0.4,0.5,0.6,0.7,0.8,0.9,1.0"}
  SEEDS=${SEEDS:-"0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19"}
  NUM_TRIALS=${NUM_TRIALS:-50}
fi

python scripts/qn_phase_sweep.py \
  --strategies BK,DQT,EQT \
  --distances "${DISTANCES}" \
  --etas "${ETAS}" \
  --seeds "${SEEDS}" \
  --num-trials "${NUM_TRIALS}" \
  --deadline-mode scaled \
  --deadline-factor ${DEADLINE_FACTOR:-1000} \
  --setup-factor ${SETUP_FACTOR:-500} \
  --min-start-delay-s ${MIN_START_DELAY_S:-0.001} \
  --mem-coh-s ${MEM_COH_S:-0.005} \
  --attn ${ATTN:-0.005} \
  --optical-eta ${OPTICAL_ETA:-0.4} \
  --fidelity ${FIDELITY:-0.5} \
  --eta-source ${ETA_SOURCE:-0.8} --eta-dest ${ETA_DEST:-0.8} \
  --dqt-eta-source ${DQT_ETA_SOURCE:-0.8} --dqt-eta-dest ${DQT_ETA_DEST:-0.8} \
  --out-dir "${OUT_DIR}"

python scripts/plot_qn_phase_sweep.py --in-agg "${OUT_DIR}/phase_agg.csv" --out-dir "${OUT_DIR}" --title "Hybrid distance×eta phase sweep (${MODE})"
