"""Explicit calibration layers for goodput-risk estimates."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyntheticGoodputCalibrator:
    """Calibration fitted only to the deterministic synthetic failure corpus.

    It must not be reused as a production calibration claim. Real trace replay
    should replace this coefficient.
    """

    scale: float = 0.50

    def apply(self, raw_risk: float) -> float:
        bounded = min(max(raw_risk, 0.0), 1.0)
        return round(min(1.0, bounded * self.scale), 6)
