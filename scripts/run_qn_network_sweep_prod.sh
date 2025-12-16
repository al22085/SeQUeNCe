#!/usr/bin/env bash
set -euo pipefail

OUT_DIR=${1:-out/qn_network_sweep_prod}

python scripts/qn_network_sweep.py \
  --strategies BK,DQT,EQT \
  --archs optical,hybrid \
  --distances 100,500,1000,2000 \
  --seeds 0,1,2,3,4,5,6,7,8,9 \
  --num-trials 20 \
  --deadline-mode scaled \
  --deadline-factor 2000 \
  --setup-factor 500 \
  --eta-source 0.8 --eta-dest 0.8 \
  --dqt-eta-source 0.8 --dqt-eta-dest 0.8 \
  --out-dir "${OUT_DIR}"

python scripts/plot_qn_network_sweep.py --in-agg "${OUT_DIR}/qn_network_agg.csv" --out-dir "${OUT_DIR}" --title "Network availability sweep"
