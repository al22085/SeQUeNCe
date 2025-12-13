"""Quantum transduction via direct conversion (thin wrapper around Layer 0 helper)."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import matplotlib.pyplot as plt

# Ensure repository root is on sys.path when running directly from source tree
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sequence.constants import KET1
from sequence.transduction.qt_layer0 import DirectConversionConfig, run_direct_conversion


DEFAULT_NUM_TRIALS = 100
DEFAULT_PERIOD = 1.0
DEFAULT_EFFICIENCY_UP = 0.5
DEFAULT_EFFICIENCY_DOWN = 0.5
DEFAULT_ATTENUATION = 0.95
DEFAULT_DISTANCE = 1e3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Direct quantum transduction demo (library-backed).")
    parser.add_argument("--num-trials", type=int, default=DEFAULT_NUM_TRIALS, help="Number of trials to run.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    parser.add_argument("--period", type=float, default=DEFAULT_PERIOD, help="Period between trials (arb. units).")
    parser.add_argument(
        "--efficiency-up",
        type=float,
        default=DEFAULT_EFFICIENCY_UP,
        help="Transducer up-conversion efficiency (sender).",
    )
    parser.add_argument(
        "--efficiency-down",
        type=float,
        default=DEFAULT_EFFICIENCY_DOWN,
        help="Transducer down-conversion efficiency (receiver).",
    )
    parser.add_argument(
        "--mw-det-eff-tx",
        type=float,
        default=1.0,
        help="Microwave detector efficiency on the sender side.",
    )
    parser.add_argument(
        "--optical-det-eff",
        type=float,
        default=1.0,
        help="Optical detector efficiency on the receiver side.",
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

    if not (0.0 <= args.efficiency_up <= 1.0 and 0.0 <= args.efficiency_down <= 1.0):
        raise ValueError("efficiency-up and efficiency-down must be between 0 and 1.")

    cfg = DirectConversionConfig(
        num_trials=args.num_trials,
        seed=args.seed,
        period=args.period,
        efficiency_up=args.efficiency_up,
        efficiency_down=args.efficiency_down,
        microwave_detector_eff_tx=args.mw_det_eff_tx,
        optical_detector_eff=args.optical_det_eff,
        attenuation=args.attenuation,
        distance=args.distance,
    )

    result = run_direct_conversion(cfg)
    stats = result.stats

    print("--------------------")
    print(f"Direct Quantum Transduction Protocol starts, the qubit that we are going to convert is: {KET1}")
    print(f"num_trials: {result.num_trials}")
    print(f"Period: {args.period}")
    print(f"Total number of photons converted: {result.num_success}")
    print(f"Conversion efficiency (no-idealities of transmon): {stats['conversion_percentage']:.2f}%")
    print("--------------------")

    # Plot1: failed/successful conversions per trial
    plt.figure(figsize=(10, 6))
    plt.plot(result.time_points, stats["failed_up_conversions"], color="blue", label="Failed Up Conversions", linewidth=2)
    plt.plot(
        result.time_points, stats["failed_down_conversions"], color="red", label="Failed Down Conversions", linewidth=2
    )
    plt.plot(
        result.time_points, stats["successful_conversions"], color="green", label="Successful Conversions", linewidth=2
    )
    plt.xlabel(r"Time ($\mu$s)", fontsize=14)
    plt.ylabel("Number of Conversions", fontsize=14)
    plt.title("Quantum Transduction Results", fontsize=16)
    plt.legend()
    plt.grid(True)
    plt.show()

    # Plot2: cumulative conversions vs ideal reference
    results_matrix = []
    for up, down, success in zip(
        stats["failed_up_conversions"], stats["failed_down_conversions"], stats["successful_conversions"]
    ):
        results_matrix.append(
            [1 if up != 0 else 0, 1 if down != 0 else 0, 1 if success != 0 else 0],
        )

    time_points = result.time_points
    ideal_photons = list(range(1, result.num_trials + 1))
    converted_photons = stats["converted_photons"]

    import numpy as np  # local import for plotting convenience

    results_matrix_np = np.array(results_matrix)

    fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(12, 8), gridspec_kw={"height_ratios": [4, 1]})

    l1, = ax1.plot(time_points, ideal_photons, "o-", label="Ideal Successfully Converted Photons", color="darkblue", markersize=3)
    l2, = ax1.plot(time_points, converted_photons, "o-", label="Successfully Converted Photons", color="#FF00FF", markersize=3)
    ax1.set_ylabel("Photon Number", fontsize=14)
    ax1.set_title("Photon Conversions over Time", fontsize=16, fontweight="bold")
    ax1.tick_params(axis="both", labelsize=12)

    b1 = ax2.bar(
        time_points,
        results_matrix_np[:, 0],
        color="#ED213C",
        label="Failed Up-conversion",
        alpha=0.8,
        width=args.period * 0.8,
        align="edge",
    )
    b2 = ax2.bar(
        time_points,
        results_matrix_np[:, 1],
        color="blue",
        label="Failed Down-conversion",
        alpha=0.8,
        bottom=results_matrix_np[:, 0],
        width=args.period * 0.8,
        align="edge",
    )
    b3 = ax2.bar(
        time_points,
        results_matrix_np[:, 2],
        color="#119B70",
        label="Successful conversions",
        alpha=0.8,
        bottom=results_matrix_np[:, 0] + results_matrix_np[:, 1],
        width=args.period * 0.8,
        align="edge",
    )
    ax2.set_xlabel(r"Time ($\mu$s)", fontsize=14)
    ax2.yaxis.set_visible(False)
    ax2.grid(True)
    ax2.tick_params(axis="both", labelsize=12)

    ax1.legend(
        handles=[l1, l2, b1, b2, b3],
        labels=[
            "Ideal Successfully Converted Photons",
            "Successfully Converted Photons",
            "Failed Up-conversion",
            "Failed Down-conversion",
            "Successful conversions",
        ],
        loc="upper left",
        fontsize=12,
        frameon=True,
        shadow=False,
    )

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.show()


if __name__ == "__main__":
    main()
