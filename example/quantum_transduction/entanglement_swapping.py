"""Quantum transduction via entanglement swapping (wrapper around Layer 0 helper)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import matplotlib.pyplot as plt

# Ensure repository root is on sys.path when running directly from source tree
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sequence.transduction.qt_layer0 import (
    EntanglementSwappingConfig,
    run_entanglement_swapping,
)


DEFAULT_NUM_TRIALS = 100
DEFAULT_PERIOD = 1.0
DEFAULT_MEASURE_DURATION = 1e-8
DEFAULT_EFFICIENCY_UP = 0.1
DEFAULT_OPTICAL_DET_EFF = 0.25
DEFAULT_ATTENUATION = 0.95
DEFAULT_DISTANCE = 1e3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Entanglement swapping demo (library-backed).")
    parser.add_argument("--num-trials", type=int, default=DEFAULT_NUM_TRIALS, help="Number of trials to run.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD, help="Period between trials (arb. units).")
    parser.add_argument(
        "--measure-duration",
        type=float,
        default=DEFAULT_MEASURE_DURATION,
        help="Time offset for measurement event scheduling.",
    )
    parser.add_argument(
        "--efficiency-up",
        type=float,
        default=DEFAULT_EFFICIENCY_UP,
        help="Transducer up-conversion efficiency for senders.",
    )
    parser.add_argument(
        "--optical-det-eff",
        type=float,
        default=DEFAULT_OPTICAL_DET_EFF,
        help="Optical detector efficiency on the middle node.",
    )
    parser.add_argument(
        "--attenuation",
        type=float,
        default=DEFAULT_ATTENUATION,
        help="Optical channel attenuation (dB/m equivalent as used in demo).",
    )
    parser.add_argument(
        "--distance",
        type=float,
        default=DEFAULT_DISTANCE,
        help="Optical channel distance (m).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    cfg = EntanglementSwappingConfig(
        num_trials=args.num_trials,
        seed=args.seed,
        period=args.period,
        measure_duration=args.measure_duration,
        efficiency_up=args.efficiency_up,
        optical_detector_eff=args.optical_det_eff,
        attenuation=args.attenuation,
        distance=args.distance,
    )

    result = run_entanglement_swapping(cfg)
    stats = result.stats

    print("--------------------")
    print("Quantum transduction via entanglement swapping")
    print(f"num_trials: {result.num_trials}")
    print(f"Percentage of Entangled pairs generated (PNRD IDEAL): {stats['percentage_detector_counters_ideal']:.2f}%")
    print(f"Percentage of Entangled pairs detected by PNRD real: {stats['percentage_detector_counters_real']:.2f}%")
    print(f"Percentage of Entangled detected by SPD IDEAL: {stats['percentage_spd_ideal']:.2f}%")
    print(f"Percentage of Entangled detected by SPD real: {stats['percentage_spd_real']:.2f}%")
    print("--------------------")

    color_blu = "#0047AB"

    plt.figure(figsize=(14, 7))

    # SPD (Single Photon Detector) counts
    plt.plot(stats["times"], stats["spd_ideals"], "o-", color="darkblue", label="SPD Ideal", markersize=4)
    plt.plot(
        stats["times"],
        stats["spd_reals"],
        "o-",
        color="darkblue",
        markerfacecolor="white",
        label="SPD Real",
        markersize=4,
    )

    # PNRD (Photon Number Resolving Detector) counts
    plt.plot(
        stats["times"],
        stats["detector_photon_counters_ideal"],
        "o-",
        color="#FF00FF",
        label="PNRD Ideal",
        markersize=4,
    )
    plt.plot(
        stats["times"],
        stats["detector_photon_counters_real"],
        "o-",
        color="#FF00FF",
        markerfacecolor="white",
        label="PNRD Real",
        markersize=4,
    )

    plt.xlabel(r"Time ($\mu$s)", fontsize=16)
    plt.ylabel("Counts", fontsize=16)
    plt.title("Ideal vs Real Counts Over Time", fontsize=18, fontweight="bold")
    plt.legend(fontsize=14)
    plt.tick_params(axis="both", which="major", labelsize=14)
    plt.show()


if __name__ == "__main__":
    main()
