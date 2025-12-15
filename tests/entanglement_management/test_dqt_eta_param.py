import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.qt_line_availability import run_experiment


@pytest.mark.parametrize("eta_source,eta_dest,expected_min,expected_max", [(0.6, 0.6, 0.0, 0.1), (1.0, 1.0, 0.2, 0.4)])
def test_dqt_eta_affects_availability_monotonic(eta_source, eta_dest, expected_min, expected_max):
    res = run_experiment(
        strategy="DQT",
        num_trials=500,
        seed=123,
        eta_source=1.0,
        eta_dest=1.0,
        qt_eff=None,
        dqt_eta_source=eta_source,
        dqt_eta_dest=eta_dest,
        distance=1e3,
        mode="fixed_attempts",
        stop_time=5e12,
    )
    avail = res["availability"]
    assert expected_min <= avail <= expected_max


def test_dqt_eta_default_matches_qt_eff_0_7():
    res_eta = run_experiment(
        strategy="DQT",
        num_trials=500,
        seed=321,
        eta_source=1.0,
        eta_dest=1.0,
        qt_eff=None,
        dqt_eta_source=1.0,
        dqt_eta_dest=0.7,
        distance=1e3,
        mode="fixed_attempts",
        stop_time=5e12,
    )
    res_qt_eff = run_experiment(
        strategy="DQT",
        num_trials=500,
        seed=321,
        eta_source=1.0,
        eta_dest=1.0,
        qt_eff=0.7,
        dqt_eta_source=1.0,
        dqt_eta_dest=1.0,
        distance=1e3,
        mode="fixed_attempts",
        stop_time=5e12,
    )
    assert res_eta["availability"] == res_qt_eff["availability"]
