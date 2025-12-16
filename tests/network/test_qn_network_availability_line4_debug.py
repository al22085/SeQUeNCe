import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.qn_network_availability_sequence import run_trials


def test_line4_ideal_has_entanglement_events():
    args = SimpleNamespace(
        strategy="BK",
        arch="optical",
        distance=1.0,
        deadline_mode="absolute",
        deadline_ps=None,
        deadline_s=0.1,
        deadline_factor=20.0,
        fiber_v=2e8,
        setup_factor=5000.0,
        min_start_delay_s=0.01,
        num_trials=5,
        seed=0,
        eta_source=1.0,
        eta_dest=1.0,
        dqt_eta_source=1.0,
        dqt_eta_dest=1.0,
        qt_eff=None,
        swap_success=1.0,
        mem_coh_s=1.0,
        attn=0.0,
        cc_delay=1e6,
        sanity="ideal",
        format="json",
        out=None,
        debug=True,
    )

    result = run_trials(args)
    dbg = result.get("debug_summary", {})
    assert dbg.get("entangled_total", 0) > 0
    assert 0.0 <= result["availability_req"] <= 1.0
