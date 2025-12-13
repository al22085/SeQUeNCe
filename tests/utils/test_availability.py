import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sequence.utils.availability import availability_from_counts, availability_from_outcomes


def test_availability_counts_zero_attempts():
    assert availability_from_counts(0, 0) == 0.0
    assert availability_from_counts(5, 0) == 0.0


def test_availability_counts_normal_case():
    assert availability_from_counts(3, 4) == 0.75


def test_availability_outcomes_iterable():
    outcomes = [True, False, True, True]
    assert availability_from_outcomes(outcomes) == 0.75
