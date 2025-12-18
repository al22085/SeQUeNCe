import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sequence.qn.strategy_params import StrategyKnobs, edge_params_for_strategy
from sequence.qn.entanglement_service import EdgeParams, SwapParams, simulate_entanglement_service


def test_strategy_params_deterministic():
    knobs = StrategyKnobs(loss_db_per_km=0.2, p_eg_per_km=None)
    p_eg, rate, coh, p_bsm, lat = edge_params_for_strategy("EQT", 100.0, 0.5, knobs)
    p_eg2, rate2, coh2, p_bsm2, lat2 = edge_params_for_strategy("EQT", 100.0, 0.5, knobs)
    assert p_eg == p_eg2
    assert rate == rate2 and coh == coh2 and p_bsm == p_bsm2 and lat == lat2


def test_availability_monotone_with_higher_p_bsm():
    edge_params = {
        tuple(sorted(("A", "R1"))): EdgeParams(1e6, 1.0, 1.0),
        tuple(sorted(("R1", "R2"))): EdgeParams(1e6, 1.0, 1.0),
        tuple(sorted(("R2", "B"))): EdgeParams(1e6, 1.0, 1.0),
    }
    res_low = simulate_entanglement_service(
        path=["A", "R1", "R2", "B"],
        edge_params=edge_params,
        swap_params=SwapParams(p_bsm=0.5, latency_s=0.0),
        seed=0,
        horizon_s=0.05,
        tau_s=0.05,
        num_requests=10,
        lambda_req=0.5,
        key_bits_per_pair=1.0,
    )
    res_high = simulate_entanglement_service(
        path=["A", "R1", "R2", "B"],
        edge_params=edge_params,
        swap_params=SwapParams(p_bsm=0.9, latency_s=0.0),
        seed=0,
        horizon_s=0.05,
        tau_s=0.05,
        num_requests=10,
        lambda_req=0.5,
        key_bits_per_pair=1.0,
    )
    assert res_high["availability"] >= res_low["availability"] - 1e-9
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
