#!/usr/bin/env bash
set -euo pipefail

OUT_DIR=${1:-out/qn_common_factor_smoke}

CAL_DIR="${OUT_DIR}/calib"
SWEEP_DIR="${OUT_DIR}/sweep"

python scripts/qn_deadline_factor_calibrate.py \
  --strategies BK,DQT,EQT \
  --archs optical,hybrid \
  --distance 1000 \
  --factors 200,500,700,1000,1500,2000,5000 \
  --seeds 0,1,2 \
  --num-trials 10 \
  --deadline-mode scaled \
  --setup-factor 500 \
  --fidelity 0.5 \
  --mem-coh-s 0.02 \
  --attn 0.0015 \
  --eta-source 0.8 --eta-dest 0.8 \
  --dqt-eta-source 0.8 --dqt-eta-dest 0.8 \
  --recommend-common-factor \
  --out-dir "${CAL_DIR}"

COMMON_OPTICAL=$(python - <<'PY'
import csv
f=open(""""${CAL_DIR}"""""/deadline_cal_common_factors.csv")
r=csv.DictReader(f)
val=1000
for row in r:
    if row["arch"]=="optical":
        val=float(row["factor"])
        break
print(int(val) if val.is_integer() else val)
PY
)
COMMON_HYBRID=$(python - <<'PY'
import csv
f=open(""""${CAL_DIR}"""""/deadline_cal_common_factors.csv")
r=csv.DictReader(f)
val=1000
for row in r:
    if row["arch"]=="hybrid":
        val=float(row["factor"])
        break
print(int(val) if val.is_integer() else val)
PY
)

python scripts/qn_network_sweep.py \
  --strategies BK,DQT,EQT \
  --archs optical \
  --distances 1000,2000 \
  --seeds 0,1,2 \
  --num-trials 10 \
  --deadline-mode scaled \
  --deadline-factor "${COMMON_OPTICAL:-1000}" \
  --setup-factor 500 \
  --mem-coh-s 0.02 \
  --attn 0.0015 \
  --fidelity 0.5 \
  --eta-source 0.8 --eta-dest 0.8 \
  --dqt-eta-source 0.8 --dqt-eta-dest 0.8 \
  --out-dir "${SWEEP_DIR}/optical"

python scripts/qn_network_sweep.py \
  --strategies BK,DQT,EQT \
  --archs hybrid \
  --distances 1000,2000 \
  --seeds 0,1,2 \
  --num-trials 10 \
  --deadline-mode scaled \
  --deadline-factor "${COMMON_HYBRID:-1000}" \
  --setup-factor 500 \
  --mem-coh-s 0.02 \
  --attn 0.0015 \
  --fidelity 0.5 \
  --eta-source 0.8 --eta-dest 0.8 \
  --dqt-eta-source 0.8 --dqt-eta-dest 0.8 \
  --out-dir "${SWEEP_DIR}/hybrid"

python scripts/plot_qn_network_sweep.py --in-agg "${SWEEP_DIR}/optical/qn_network_agg.csv" --out-dir "${SWEEP_DIR}/optical" --title "Network availability sweep (optical common factor)"
python scripts/plot_qn_network_sweep.py --in-agg "${SWEEP_DIR}/hybrid/qn_network_agg.csv" --out-dir "${SWEEP_DIR}/hybrid" --title "Network availability sweep (hybrid common factor)"
