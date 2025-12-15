#!/usr/bin/env bash
set -euo pipefail

# Repro command for EQT vs DQT eta sweep comparison (fixed_attempts).
OUT_DIR=${1:-out/qt_eta_compare_d1e3}

python scripts/qt_line_eta_sweep.py \
  --protocols EQT,DQT \
  --distance 1e3 \
  --etas 0.4,0.5,0.6,0.7,0.8,0.9,1.0 \
  --seeds 0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19 \
  --attempts 1000 \
  --out-dir "${OUT_DIR}"
