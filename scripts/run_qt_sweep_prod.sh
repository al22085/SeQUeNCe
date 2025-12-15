#!/usr/bin/env bash
set -euo pipefail

# Repro command for production-quality availability curves (fixed_attempts).
OUT_DIR=${1:-out/qt_sweep_prod_eta0p8}

python scripts/qt_line_sweep.py \
  --strategies BK,DQT,EQT \
  --distances 5e2,1e3,2e3,5e3,1e4 \
  --seeds 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 \
  --attempts 1000 \
  --eta-source 0.8 \
  --eta-dest 0.8 \
  --out-dir "${OUT_DIR}"

python scripts/plot_qt_line_sweep.py \
  --in-agg "${OUT_DIR}/qt_line_agg.csv" \
  --out-dir "${OUT_DIR}/figs" \
  --title "QT line availability (fixed_attempts, attempts=1000, seeds=0..19, eta=0.8)"
