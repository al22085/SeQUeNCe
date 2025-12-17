#!/usr/bin/env bash
set -euo pipefail

OUT_DIR=${1:-out/qn_phase_prod}

python scripts/qn_phase_sweep.py \
  --strategies BK,DQT,EQT \
  --distances 500,1000,2000 \
  --etas 0.4,0.5,0.6,0.7,0.8,0.9,1.0 \
  --seeds 0,1,2,3,4 \
  --num-trials 15 \
  --deadline-mode scaled \
  --deadline-factor 1000 \
  --setup-factor 500 \
  --min-start-delay-s 0.001 \
  --mem-coh-s 0.005 \
  --attn 0.005 \
  --optical-eta 0.4 \
  --fidelity 0.5 \
  --eta-source 0.8 --eta-dest 0.8 \
  --dqt-eta-source 0.8 --dqt-eta-dest 0.8 \
  --out-dir "${OUT_DIR}"

python scripts/plot_qn_phase_sweep.py --in-agg "${OUT_DIR}/phase_agg.csv" --out-dir "${OUT_DIR}" --title "Hybrid distance×eta phase sweep"
