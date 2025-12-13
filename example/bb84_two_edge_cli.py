"""Minimal two-node BB84 CLI that pairs roles before timeline init."""

from __future__ import annotations

import argparse
from typing import Any, Dict

from sequence.components.optical_channel import ClassicalChannel, QuantumChannel
from sequence.kernel.event import Event
from sequence.kernel.process import Process
from sequence.kernel.timeline import Timeline
from sequence.qkd.BB84 import pair_bb84_protocols
from sequence.topology.node import QKDNode


DEFAULT_DISTANCE = 1e3
DEFAULT_RUNTIME = 5e9
DEFAULT_KEY_LENGTH = 256
DEFAULT_KEY_NUM = 1
DEFAULT_MEAN_PHOTON_NUM = 0.1
DEFAULT_FREQUENCY = 80e6


def _build_qkd_nodes(tl: Timeline, distance: float, seed: int | None) -> tuple[QKDNode, QKDNode]:
    """Create two QKD nodes and connect symmetric classical/quantum channels."""
    qc_ab = QuantumChannel("qc_ab", tl, distance=distance, polarization_fidelity=0.97, attenuation=0.0002)
    qc_ba = QuantumChannel("qc_ba", tl, distance=distance, polarization_fidelity=0.97, attenuation=0.0002)
    cc_ab = ClassicalChannel("cc_ab", tl, distance=distance)
    cc_ba = ClassicalChannel("cc_ba", tl, distance=distance)
    cc_ab.delay += 1e9
    cc_ba.delay += 1e9

    alice = QKDNode("alice", tl, stack_size=1)
    bob = QKDNode("bob", tl, stack_size=1)

    if seed is not None:
        alice.set_seed(seed)
        bob.set_seed(seed + 1)

    ls_params = {"frequency": DEFAULT_FREQUENCY, "mean_photon_num": DEFAULT_MEAN_PHOTON_NUM}
    for name, value in ls_params.items():
        alice.update_lightsource_params(name, value)

    detector_params = [
        {"efficiency": 0.8, "dark_count": 10, "time_resolution": 10, "count_rate": 50e6},
        {"efficiency": 0.8, "dark_count": 10, "time_resolution": 10, "count_rate": 50e6},
    ]
    for i, params in enumerate(detector_params):
        for name, value in params.items():
            bob.update_detector_params(i, name, value)

    qc_ab.set_ends(alice, bob.name)
    qc_ba.set_ends(bob, alice.name)
    cc_ab.set_ends(alice, bob.name)
    cc_ba.set_ends(bob, alice.name)

    # Critical: set BB84 roles before tl.init() to avoid role==-1 assertion.
    pair_bb84_protocols(alice.protocol_stack[0], bob.protocol_stack[0])

    return alice, bob


def run_bb84_two_edge(
    distance: float = DEFAULT_DISTANCE,
    runtime: float = DEFAULT_RUNTIME,
    key_length: int = DEFAULT_KEY_LENGTH,
    key_num: int = DEFAULT_KEY_NUM,
    seed: int | None = None,
) -> Dict[str, Any]:
    """Run a short BB84 simulation between two nodes."""
    tl = Timeline(runtime)
    tl.show_progress = False

    alice, bob = _build_qkd_nodes(tl, distance=distance, seed=seed)

    process = Process(alice.protocol_stack[0], "push", [key_length, key_num, runtime / 2])
    tl.schedule(Event(0, process))

    tl.init()
    tl.run()

    proto = alice.protocol_stack[0]
    throughput = proto.throughputs[-1] if proto.throughputs else 0.0
    error_rate = proto.error_rates[-1] if proto.error_rates else 0.0
    generated = proto.key_bits if proto.key_bits is not None else []

    return {
        "alice_role": proto.role,
        "bob_role": bob.protocol_stack[0].role,
        "throughput": throughput,
        "error_rate": error_rate,
        "generated_bits": list(generated),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a minimal two-node BB84 simulation.")
    parser.add_argument("--distance", type=float, default=DEFAULT_DISTANCE, help="Fiber distance (m).")
    parser.add_argument("--runtime", type=float, default=DEFAULT_RUNTIME, help="Timeline stop time.")
    parser.add_argument("--key-length", type=int, default=DEFAULT_KEY_LENGTH, help="Key length to request.")
    parser.add_argument("--key-num", type=int, default=DEFAULT_KEY_NUM, help="Number of keys to request.")
    parser.add_argument("--seed", type=int, default=None, help="Base RNG seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_bb84_two_edge(
        distance=args.distance,
        runtime=args.runtime,
        key_length=args.key_length,
        key_num=args.key_num,
        seed=args.seed,
    )

    print("--- BB84 two-edge CLI ---")
    print(f"alice_role={result['alice_role']}, bob_role={result['bob_role']}")
    print(f"throughput={result['throughput']:.4g}, error_rate={result['error_rate']:.4g}")
    print(f"generated_bits={len(result['generated_bits'])}")


if __name__ == "__main__":
    main()
