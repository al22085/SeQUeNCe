"""Layer 0 helpers for QT hardware demos (direct conversion & entanglement swapping).

These helpers mirror the existing demo scripts under ``example/quantum_transduction``
but expose them as reusable functions so higher layers can call into the same setups.
"""

from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Any, Dict, List, Optional

import numpy as np

from example.quantum_transduction.fock_quantum_channel import FockQuantumChannel
from example.quantum_transduction.swapping_protocols import Measure, Swapping
from sequence.components.beam_splitter import FockBeamSplitter2
from sequence.components.detector import FockDetector
from sequence.components.transducer import (
    MICROWAVE_WAVELENGTH,
    OPTICAL_WAVELENGTH,
    DownConversionProtocol,
    Transducer,
    UpConversionProtocol,
)
from sequence.components.transmon import EmittingProtocol, Transmon
from sequence.constants import KET0, KET1
from sequence.kernel.event import Event
from sequence.kernel.process import Process
from sequence.kernel.timeline import Timeline
from sequence.topology.node import Node


class _Counter:
    """Simple trigger counter used by the demo components."""

    def __init__(self) -> None:
        self.count = 0

    def trigger(self, _detector: Any, _info: Any) -> None:
        self.count += 1


def _set_seed(seed: Optional[int]) -> None:
    """Seed numpy / random for reproducibility."""
    if seed is None:
        return
    np.random.seed(seed)
    random.seed(seed)


@dataclass
class DirectConversionConfig:
    num_trials: int
    seed: Optional[int] = None
    runtime: float = 1e13
    start_time: float = 0.0
    period: float = 1.0
    microwave_wavelength: int = MICROWAVE_WAVELENGTH
    optical_wavelength: int = OPTICAL_WAVELENGTH
    transmon_efficiency: float = 1.0
    efficiency_up: float = 0.5
    efficiency_down: float = 0.5
    microwave_detector_eff_tx: float = 1.0
    microwave_detector_eff_rx: float = 1.0
    optical_detector_eff: float = 1.0
    attenuation: float = 0.95
    distance: float = 1e3


@dataclass
class DirectConversionResult:
    num_trials: int
    num_success: int
    total_emitted: int
    failed_up_conversions: List[int]
    failed_down_conversions: List[int]
    successful_conversions: List[int]
    emitted_photons: List[int]
    converted_photons: List[int]
    time_points: List[float]
    stats: Dict[str, Any]


class _SenderNode(Node):
    """Sender node for the direct-conversion demo (transmon + detector + transducer)."""

    def __init__(self, name: str, timeline: Timeline, cfg: DirectConversionConfig) -> None:
        super().__init__(name, timeline)

        wavelengths = [cfg.microwave_wavelength, cfg.optical_wavelength]
        state_list = [KET1, KET0]

        # transmon
        transmon_name = f"{name}.transmon"
        transmon = Transmon(
            name=transmon_name,
            owner=self,
            timeline=timeline,
            wavelengths=wavelengths,
            photon_counter=0,
            efficiency=cfg.transmon_efficiency,
            photons_quantum_state=state_list,
        )
        self.add_component(transmon)

        # detector
        detector_name = f"{name}.fockdetector"
        detector = FockDetector(
            detector_name,
            timeline,
            wavelength=cfg.microwave_wavelength,
            efficiency=cfg.microwave_detector_eff_tx,
        )
        self.add_component(detector)
        self.counter_tx = _Counter()
        detector.attach(self.counter_tx)

        # transducer
        transducer_name = f"{name}.transducer"
        transducer = Transducer(name=transducer_name, owner=self, timeline=timeline, efficiency=cfg.efficiency_up)
        self.add_component(transducer)
        transducer.attach(self)
        self.counter_transducer = _Counter()
        transducer.attach(self.counter_transducer)

        # emitting protocol and upconversion protocol
        self.emitting_protocol = EmittingProtocol(self, f"{name}.emitting_protocol", timeline, transmon, transducer)
        transducer.up_conversion_protocol = UpConversionProtocol(self, f"{name}.up_conversion_protocol", timeline, transducer)


class _ReceiverNode(Node):
    """Receiver node for the direct-conversion demo (transmon + detector + transducer)."""

    def __init__(self, name: str, timeline: Timeline, cfg: DirectConversionConfig) -> None:
        super().__init__(name, timeline)

        wavelengths = [cfg.microwave_wavelength, cfg.optical_wavelength]
        state_list = [KET1, KET0]

        self.transmon_name = f"{name}.transmon"
        self.detector_name = f"{name}.fockdetector"
        self.counter_rx = _Counter()
        self.transducer_name = f"{name}.transducer"
        self.counter_transducer = _Counter()
        self.first_component_name = self.transducer_name

        # transmon
        transmon = Transmon(
            name=self.transmon_name,
            owner=self,
            timeline=timeline,
            wavelengths=wavelengths,
            photons_quantum_state=state_list,
            photon_counter=0,
            efficiency=1.0,
        )
        self.add_component(transmon)

        # fock detector
        detector = FockDetector(
            self.detector_name,
            timeline,
            wavelength=cfg.optical_wavelength,
            efficiency=cfg.optical_detector_eff,
        )
        self.add_component(detector)
        detector.attach(self.counter_rx)

        # transducer
        transducer = Transducer(name=self.transducer_name, owner=self, timeline=timeline, efficiency=cfg.efficiency_down)
        self.add_component(transducer)
        transducer.attach(self)
        transducer.attach(self.counter_transducer)

        self.set_first_component(self.transducer_name)
        transducer.add_outputs([transmon, detector])

        transducer.down_conversion_protocol = DownConversionProtocol(self, f"{name}.down_conversion_protocol", timeline, transducer)


def run_direct_conversion(config: DirectConversionConfig) -> DirectConversionResult:
    """Run the direct-conversion demo for ``config.num_trials`` and return counts."""
    _set_seed(config.seed)

    tl = Timeline(config.runtime)
    sender = _SenderNode("node1", tl, config)
    receiver = _ReceiverNode("node2", tl, config)

    qc = FockQuantumChannel("qc.node1.node2", tl, attenuation=config.attenuation, distance=config.distance)
    qc.set_ends(sender, receiver)

    # Node1
    transmon1 = sender.get_components_by_type("Transmon")[0]
    transducer1 = sender.get_components_by_type("Transducer")[0]
    detector1 = sender.get_components_by_type("FockDetector")[0]
    transmon1.add_receiver(transducer1)
    transducer1.add_outputs([qc, detector1])

    # Node2
    transmon2 = receiver.get_components_by_type("Transmon")[0]
    transducer2 = receiver.get_components_by_type("Transducer")[0]
    detector2 = receiver.get_components_by_type("FockDetector")[0]

    failed_up_conversions: List[int] = []
    failed_down_conversions: List[int] = []
    successful_conversions: List[int] = []

    ideal_photons: List[int] = []
    emitted_photons: List[int] = []
    converted_photons: List[int] = []
    time_points: List[float] = []

    total_photons_successful = 0
    total_transducer_count = 0
    cumulative_time = config.start_time

    for trial in range(config.num_trials):
        tl.time = 0
        tl.init()

        detector1.photon_counter = 0
        transmon2.photon_counter = 0
        detector2.photon_counter = 0

        process0 = Process(sender.emitting_protocol, "start", [])
        event_time0 = cumulative_time
        event0 = Event(event_time0, process0)
        tl.schedule(event0)

        tl.run()

        failed_up_conversions.append(detector1.photon_counter)
        failed_down_conversions.append(detector2.photon_counter)
        successful_conversions.append(transmon2.photon_counter)

        total_photons_successful += transmon2.photon_counter

        total_transducer_count += transducer1.photon_counter
        cumulative_time += config.period

        ideal_photons.append(trial + 1)
        emitted_photons.append(total_transducer_count)
        converted_photons.append(total_photons_successful)
        time_points.append(trial * config.period)

    total_photons_to_be_converted = config.num_trials
    conversion_percentage = (
        (total_photons_successful / total_photons_to_be_converted) * 100 if total_photons_to_be_converted > 0 else 0
    )

    stats: Dict[str, Any] = {
        "failed_up_conversions": failed_up_conversions,
        "failed_down_conversions": failed_down_conversions,
        "successful_conversions": successful_conversions,
        "ideal_photons": ideal_photons,
        "emitted_photons": emitted_photons,
        "converted_photons": converted_photons,
        "conversion_percentage": conversion_percentage,
    }

    return DirectConversionResult(
        num_trials=config.num_trials,
        num_success=total_photons_successful,
        total_emitted=total_photons_to_be_converted,
        failed_up_conversions=failed_up_conversions,
        failed_down_conversions=failed_down_conversions,
        successful_conversions=successful_conversions,
        emitted_photons=emitted_photons,
        converted_photons=converted_photons,
        time_points=time_points,
        stats=stats,
    )


@dataclass
class EntanglementSwappingConfig:
    num_trials: int
    seed: Optional[int] = None
    runtime: float = 1e13
    start_time: float = 0.0
    period: float = 1.0
    measure_duration: float = 1e-8
    microwave_wavelength: int = MICROWAVE_WAVELENGTH
    optical_wavelength: int = OPTICAL_WAVELENGTH
    transmon_efficiency: float = 1.0
    efficiency_up: float = 0.1
    optical_detector_eff: float = 0.25
    attenuation: float = 0.95
    distance: float = 1e3


@dataclass
class EntanglementSwappingResult:
    num_trials: int
    num_success: int
    stats: Dict[str, Any]


class _SwappingSenderNode(Node):
    """End node for entanglement swapping demo."""

    def __init__(self, name: str, timeline: Timeline, cfg: EntanglementSwappingConfig) -> None:
        super().__init__(name, timeline)

        wavelengths = [cfg.microwave_wavelength, cfg.optical_wavelength]
        state_list = [KET1, KET0]

        transmon0_name = f"{name}.transmon0"
        transmon0 = Transmon(
            name=transmon0_name,
            owner=self,
            timeline=timeline,
            wavelengths=wavelengths,
            photon_counter=0,
            efficiency=1.0,
            photons_quantum_state=state_list,
        )
        self.add_component(transmon0)

        transducer_name = f"{name}.transducer"
        transducer = Transducer(name=transducer_name, owner=self, timeline=timeline, efficiency=cfg.efficiency_up)
        self.add_component(transducer)
        transducer.attach(self)
        transducer.photon_counter = 0
        self.counter = _Counter()
        transducer.attach(self.counter)

        transmon0.add_receiver(transducer)

        transmon_name = f"{name}.transmon"
        transmon = Transmon(
            name=transmon_name,
            owner=self,
            timeline=timeline,
            wavelengths=wavelengths,
            photon_counter=0,
            efficiency=1.0,
            photons_quantum_state=state_list,
        )
        self.add_component(transmon)

        self.emitting_protocol = EmittingProtocol(self, f"{name}.emitting_protocol", timeline, transmon0, transducer)
        transducer.up_conversion_protocol = UpConversionProtocol(self, f"{name}.up_conversion_protocol", timeline, transducer)


class _EntangleNode(Node):
    """Middle node hosting the beam splitter and detectors for swapping."""

    def __init__(self, name: str, timeline: Timeline, src_list: List[str], cfg: EntanglementSwappingConfig) -> None:
        super().__init__(name, timeline)

        self.fock_beam_splitter_name = f"{name}.FockBeamSplitter"
        fock_beam_splitter = FockBeamSplitter2(
            name=self.fock_beam_splitter_name,
            owner=self,
            timeline=timeline,
            efficiency=0.5,
            photon_counter=0,
            src_list=src_list,
        )
        self.add_component(fock_beam_splitter)

        self.set_first_component(self.fock_beam_splitter_name)

        detector_name = f"{name}.detector1"
        detector = FockDetector(detector_name, timeline, efficiency=cfg.optical_detector_eff)
        self.add_component(detector)

        detector_name2 = f"{name}.detector2"
        detector2 = FockDetector(detector_name2, timeline, efficiency=cfg.optical_detector_eff)
        self.add_component(detector2)

        fock_beam_splitter.add_outputs([detector, detector2])

        self.counter = _Counter()
        self.counter2 = _Counter()

        detector.attach(self.counter)
        detector2.attach(self.counter2)

        self.swapping_protocol = Swapping(self, f"{name}.swapping_protocol", timeline, fock_beam_splitter)
        self.measure_protocol = Measure(self, f"{name}.measure_protocol", timeline, fock_beam_splitter)

        fock_beam_splitter.swapping_protocol = self.swapping_protocol


def run_entanglement_swapping(config: EntanglementSwappingConfig) -> EntanglementSwappingResult:
    """Run the entanglement-swapping demo for ``config.num_trials`` and return counts."""
    _set_seed(config.seed)

    tl = Timeline(config.runtime)

    node1 = _SwappingSenderNode("node1", tl, config)
    node3 = _SwappingSenderNode("node3", tl, config)

    qc1 = FockQuantumChannel("qc.node1.node2", tl, attenuation=config.attenuation, distance=config.distance)
    qc2 = FockQuantumChannel("qc.node3.node2", tl, attenuation=config.attenuation, distance=config.distance)

    src_list = [qc1, qc2]
    node2 = _EntangleNode("node2", tl, src_list, config)

    qc1.set_ends(node1, node2)
    qc2.set_ends(node3, node2)

    times: List[float] = []
    detector_photon_counters_real: List[int] = []
    spd_reals: List[int] = []
    detector_photon_counters_ideal: List[int] = []
    spd_ideals: List[int] = []
    total_emitted_photons = config.num_trials
    detector_photon_counter_ideal = 0
    detector_photon_counter_real = 0
    spd_ideal = 0
    spd_real = 0

    # Node1 and Node3 (Sender nodes)
    transmon0 = node1.get_components_by_type("Transmon")[0]
    transducer = node1.get_components_by_type("Transducer")[0]
    transmon = node1.get_components_by_type("Transmon")[1]

    transmon0.add_receiver(transducer)
    transducer.add_outputs([qc1, transmon])

    transmon1 = node3.get_components_by_type("Transmon")[0]

    transducer2 = node3.get_components_by_type("Transducer")[0]
    transmon2 = node3.get_components_by_type("Transmon")[1]

    transmon.add_receiver(transducer2)
    transducer2.add_outputs([qc2, transmon2])

    # Node2 (Entangle node)
    fock_beam_splitter = node2.get_components_by_type("FockBeamSplitter2")[0]

    detector1 = node2.get_components_by_type("FockDetector")[0]
    detector2 = node2.get_components_by_type("FockDetector")[1]

    cumulative_time = config.start_time

    for trial in range(config.num_trials):
        tl.time = 0
        tl.init()

        transducer.photon_counter = 0
        transducer2.photon_counter = 0
        fock_beam_splitter.photon_counter = 0
        detector1.photon_counter = 0
        detector2.photon_counter = 0
        detector1.photon_counter2 = 0
        detector2.photon_counter2 = 0

        process0 = Process(node1.emitting_protocol, "start", [])
        event_time0 = cumulative_time
        event0 = Event(event_time0, process0)
        tl.schedule(event0)

        process2 = Process(node3.emitting_protocol, "start", [])
        event2 = Event(event_time0, process2)
        tl.schedule(event2)

        process3 = Process(node2.measure_protocol, "start", [])
        event_time3 = event_time0 + config.measure_duration
        event3 = Event(event_time3, process3)
        tl.schedule(event3)

        tl.run()

        detector_photon_counter_ideal = node2.measure_protocol.detector_photon_counter_ideal
        spd_ideal = node2.measure_protocol.spd_ideal
        detector_photon_counter_real = node2.measure_protocol.detector_photon_counter_real
        spd_real = node2.measure_protocol.spd_real

        times.append(trial * config.period)
        detector_photon_counters_real.append(detector_photon_counter_real)
        spd_reals.append(spd_real)
        detector_photon_counters_ideal.append(detector_photon_counter_ideal)
        spd_ideals.append(spd_ideal)

        cumulative_time += config.period

    percentage_detector_counters_ideal = (
        (detector_photon_counter_ideal / total_emitted_photons) * 100 if total_emitted_photons > 0 else 0
    )
    percentage_detector_counters_real = (
        (detector_photon_counter_real / total_emitted_photons) * 100 if total_emitted_photons > 0 else 0
    )
    percentage_spd_ideal = (spd_ideal / total_emitted_photons) * 100 if total_emitted_photons > 0 else 0
    percentage_spd_real = (spd_real / total_emitted_photons) * 100 if total_emitted_photons > 0 else 0

    stats = {
        "times": times,
        "detector_photon_counters_real": detector_photon_counters_real,
        "spd_reals": spd_reals,
        "detector_photon_counters_ideal": detector_photon_counters_ideal,
        "spd_ideals": spd_ideals,
        "percentage_detector_counters_ideal": percentage_detector_counters_ideal,
        "percentage_detector_counters_real": percentage_detector_counters_real,
        "percentage_spd_ideal": percentage_spd_ideal,
        "percentage_spd_real": percentage_spd_real,
    }

    return EntanglementSwappingResult(
        num_trials=config.num_trials,
        num_success=detector_photon_counter_real,
        stats=stats,
    )


__all__ = [
    "DirectConversionConfig",
    "DirectConversionResult",
    "EntanglementSwappingConfig",
    "EntanglementSwappingResult",
    "run_direct_conversion",
    "run_entanglement_swapping",
]
