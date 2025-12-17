"""Sweep crossover sensitivity vs a single physical knob."""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
from pathlib import Path
from typing import List

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_phase_sweep import parse_list
from scripts.plot_qn_phase_sweep import read_agg
from scripts.qn_experiment_presets import apply_preset


def run_phase(args, out_dir: Path, knob_name: str, knob_value: float, env: dict):
    cmd = [
        sys.executable,
        "scripts/qn_phase_sweep.py",
        "--strategies",
        args.strategies,
        "--distances",
        args.distances,
        "--etas",
        args.etas,
        "--seeds",
        args.seeds,
        "--num-trials",
        str(args.num_trials),
        "--deadline-mode",
        args.deadline_mode,
        "--deadline-factor",
        str(args.deadline_factor),
        "--setup-factor",
        str(args.setup_factor),
        "--min-start-delay-s",
        str(args.min_start_delay_s),
        "--mem-coh-s",
        str(args.mem_coh_s if knob_name != "mem_coh_s" else knob_value),
        "--attn",
        str(args.attn if knob_name != "attn" else knob_value),
        "--optical-eta",
        str(args.optical_eta if knob_name != "optical_eta" else knob_value),
        "--fidelity",
        str(args.fidelity),
        "--eta-source",
        str(args.eta_source),
        "--eta-dest",
        str(args.eta_dest),
        "--dqt-eta-source",
        str(args.dqt_eta_source),
        "--dqt-eta-dest",
        str(args.dqt_eta_dest),
        "--workers",
        str(env.get("WORKERS", 1)),
        "--out-dir",
        str(out_dir),
    ]
    subprocess.run(cmd, check=True, env=env)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Crossover sensitivity over one knob.")
    p.add_argument("--knob", choices=["mem_coh_s", "attn", "optical_eta"], default="mem_coh_s")
    p.add_argument("--values", default="0.002,0.005,0.01")
    p.add_argument("--strategies", default="BK,DQT,EQT")
    p.add_argument("--distances", default="1000,2000")
    p.add_argument("--etas", default="0.4,0.6,0.8,1.0")
    p.add_argument("--seeds", default="0,1,2")
    p.add_argument("--num-trials", type=int, default=10)
    p.add_argument("--deadline-mode", choices=["absolute", "scaled"], default="scaled")
    p.add_argument("--deadline-factor", type=float, default=1000.0)
    p.add_argument("--setup-factor", type=float, default=500.0)
    p.add_argument("--min-start-delay-s", type=float, default=0.001)
    p.add_argument("--mem-coh-s", type=float, default=0.005)
    p.add_argument("--attn", type=float, default=0.005)
    p.add_argument("--optical-eta", type=float, default=0.4)
    p.add_argument("--fidelity", type=float, default=0.5)
    p.add_argument("--eta-source", type=float, default=0.8)
    p.add_argument("--eta-dest", type=float, default=0.8)
    p.add_argument("--dqt-eta-source", type=float, default=0.8)
    p.add_argument("--dqt-eta-dest", type=float, default=0.8)
    p.add_argument("--preset", type=str, default="", help="Named preset from qn_experiment_presets.py")
    p.add_argument("--out-dir", type=Path, default=Path("out/qn_crossover_sensitivity"))
    p.add_argument("--workers", type=int, default=4, help="Parallel workers (capped at 4) for inner sweeps.")
    return p.parse_args()


def main():
    args = parse_args()
    args = apply_preset(args, args.preset)
    values = parse_list(args.values, float)
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    sens_rows = []
    for v in values:
        sweep_dir = out_dir / f"{args.knob}_{v}"
        # force inner worker cap between 2 and 4 unless user set 1 for tiny sweeps
        inner_workers = args.workers
        if inner_workers < 1:
            inner_workers = 1
        if inner_workers > 4:
            inner_workers = 4
        env = dict(**os.environ, WORKERS=str(inner_workers))
        run_phase(args, sweep_dir, args.knob, v, env)
        agg_path = sweep_dir / "phase_agg.csv"
        _, bk_map, eqt_map = read_agg(agg_path)
        dists = sorted({d for emap in bk_map.values() for d in emap.keys()})
        etas = sorted(bk_map.keys())
        for d in dists:
            eta_vals = sorted(etas)
            bk_vals = [bk_map.get(e, {}).get(d, np.nan) for e in eta_vals]
            eqt_vals = [eqt_map.get(e, {}).get(d, np.nan) for e in eta_vals]
            eta_cross = np.nan
            for i, e in enumerate(eta_vals):
                diff = eqt_vals[i] - bk_vals[i]
                if np.isnan(diff):
                    continue
                if diff >= 0:
                    if i == 0:
                        eta_cross = e
                    else:
                        prev_diff = eqt_vals[i - 1] - bk_vals[i - 1]
                        prev_eta = eta_vals[i - 1]
                        if np.isnan(prev_diff):
                            eta_cross = e
                        else:
                            if diff == prev_diff:
                                eta_cross = e
                            else:
                                eta_cross = prev_eta + (e - prev_eta) * (-prev_diff) / (diff - prev_diff)
                    break
            sens_rows.append((args.knob, v, d, eta_cross))

    sens_path = out_dir / "crossover_sensitivity.csv"
    with sens_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["knob", "value", "distance", "eta_crossover"])
        writer.writerows(sens_rows)
    print(f"Wrote {sens_path}")


if __name__ == "__main__":
    main()
