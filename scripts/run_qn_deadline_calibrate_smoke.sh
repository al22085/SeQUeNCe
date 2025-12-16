#!/usr/bin/env bash
set -euo pipefail

OUT_DIR=${1:-out/qn_deadline_cal_smoke}

python scripts/qn_deadline_factor_calibrate.py \
  --strategies BK,EQT \
  --archs optical,hybrid \
  --distance 1000 \
  --factors 50,100,200,500,1000,2000 \
  --seeds 0,1,2 \
  --num-trials 10 \
  --deadline-mode scaled \
  --setup-factor 500 \
  --fidelity 0.5 \
  --eta-source 0.8 --eta-dest 0.8 \
  --dqt-eta-source 0.8 --dqt-eta-dest 0.8 \
  --out-dir "${OUT_DIR}"

python scripts/plot_qn_deadline_factor_calibrate.py \
  --in-agg "${OUT_DIR}/deadline_cal_agg.csv" \
  --out-dir "${OUT_DIR}" \
  --title "Deadline factor calibration (smoke)"
