"""Shared availability metric helpers."""

from __future__ import annotations

from typing import Iterable


def availability_from_counts(successes: int, attempts: int) -> float:
    """Compute availability = successes / attempts; returns 0.0 if attempts == 0."""
    if attempts <= 0:
        return 0.0
    return successes / attempts


def availability_from_outcomes(outcomes: Iterable[bool]) -> float:
    """Compute availability from an iterable of boolean outcomes (True = success)."""
    successes = 0
    attempts = 0
    for outcome in outcomes:
        attempts += 1
        successes += 1 if outcome else 0
    return availability_from_counts(successes, attempts)


__all__ = ["availability_from_counts", "availability_from_outcomes"]
