"""Round a metric to one decimal place.

The generator and the metrics agent both use this helper. The formulas stay
in their own modules.
"""

from __future__ import annotations


def round_1(value: float) -> float:
    return round(float(value), 1)


def percent(part: int, whole: int) -> float:
    if whole == 0:
        return 0.0
    return round_1(100 * part / whole)
