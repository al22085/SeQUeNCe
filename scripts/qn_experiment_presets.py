"""Named experiment presets for phase/sensitivity sweeps."""

PRESETS = {
    "preset_non_saturated_smoke": {
        "strategies": "BK,DQT,EQT",
        "distances": "1000,2000",
        "etas": "0.6,0.8,1.0",
        "seeds": "0,1",
        "num_trials": 5,
        "deadline_mode": "scaled",
        "deadline_factor": 1000,
        "setup_factor": 500,
        "min_start_delay_s": 0.001,
        "mem_coh_s": 0.005,
        "attn": 0.005,
        "optical_eta": 0.4,
        "fidelity": 0.5,
        "eta_source": 0.8,
        "eta_dest": 0.8,
        "dqt_eta_source": 0.8,
        "dqt_eta_dest": 0.8,
        "workers": 2,
    },
    "preset_hybrid_phase_default": {
        "strategies": "BK,DQT,EQT",
        "distances": "500,1000,2000,5000",
        "etas": "0.4,0.5,0.6,0.7,0.8,0.9,1.0",
        "seeds": "0,1,2,3,4,5,6,7,8,9",
        "num_trials": 30,
        "deadline_mode": "scaled",
        "deadline_factor": 1000,
        "setup_factor": 500,
        "min_start_delay_s": 0.001,
        "mem_coh_s": 0.005,
        "attn": 0.005,
        "optical_eta": 0.4,
        "fidelity": 0.5,
        "eta_source": 0.8,
        "eta_dest": 0.8,
        "dqt_eta_source": 0.8,
        "dqt_eta_dest": 0.8,
        "workers": 4,
    },
    "preset_sensitivity_attn_default": {
        "knob": "attn",
        "values": "0.002,0.005,0.01",
        "strategies": "BK,DQT,EQT",
        "distances": "1000,2000",
        "etas": "0.6,1.0",
        "seeds": "0,1,2,3,4",
        "num_trials": 10,
        "deadline_mode": "scaled",
        "deadline_factor": 1000,
        "setup_factor": 500,
        "min_start_delay_s": 0.001,
        "mem_coh_s": 0.005,
        "attn": 0.005,
        "optical_eta": 0.4,
        "fidelity": 0.5,
        "eta_source": 0.8,
        "eta_dest": 0.8,
        "dqt_eta_source": 0.8,
        "dqt_eta_dest": 0.8,
        "workers": 4,
    },
}


def apply_preset(ns, preset_name: str):
    """Apply preset defaults into an argparse Namespace if present."""
    if not preset_name:
        return ns
    preset = PRESETS.get(preset_name)
    if not preset:
        raise ValueError(f"Unknown preset: {preset_name}")
    for k, v in preset.items():
        # Only set if user left default value (None or falsy in some cases)
        if not hasattr(ns, k):
            continue
        current = getattr(ns, k)
        if current is None or (isinstance(current, (int, float)) and current == 0) or (isinstance(current, str) and current == ""):
            setattr(ns, k, v)
    # Always apply recommended workers if present (but CLI can override)
    if hasattr(ns, "workers") and getattr(ns, "workers", None) in (None, 0):
        if "workers" in preset:
            ns.workers = preset["workers"]
    return ns
