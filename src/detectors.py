"""Bounded anomaly, trend, entropy, and metric-direction policies."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict, deque
from typing import Deque, MutableMapping, Optional, Sequence, Tuple

from control_types import Signal, TelemetrySample


class RollingBaselineDetector:
    """Score samples against the prior window before incorporating them."""

    def __init__(self, window: int = 64, warmup: int = 12, z_threshold: float = 2.5) -> None:
        if warmup < 3 or warmup >= window:
            raise ValueError("warmup must be >= 3 and < window")
        self.window = window
        self.warmup = warmup
        self.z_threshold = z_threshold
        self._values: MutableMapping[Tuple[str, str], Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.window)
        )

    def ingest(self, sample: TelemetrySample) -> Optional[Signal]:
        key = (sample.component_id, sample.metric)
        values = self._values[key]
        signal: Optional[Signal] = None
        if len(values) >= self.warmup:
            mean = statistics.fmean(values)
            std = statistics.pstdev(values)
            robust_scale = max(std, abs(mean) * 0.01, 1e-6)
            z = (sample.value - mean) / robust_scale
            if abs(z) >= self.z_threshold:
                signal = Signal(
                    component_id=sample.component_id,
                    metric=sample.metric,
                    score=min(1.0, abs(z) / 6.0),
                    direction="up" if z > 0 else "down",
                    detector="rolling_z",
                    timestamp=sample.timestamp,
                    evidence={
                        "z": round(z, 6),
                        "baseline_mean": round(mean, 6),
                        "baseline_std": round(std, 6),
                    },
                )
        values.append(sample.value)
        return signal

    def trend_signal(
        self,
        component_id: str,
        metric: str,
        timestamp: float,
        span: int = 8,
    ) -> Optional[Signal]:
        values = list(self._values[(component_id, metric)])
        if len(values) < span * 2:
            return None
        older = values[-2 * span : -span]
        recent = values[-span:]
        older_mean = statistics.fmean(older)
        recent_mean = statistics.fmean(recent)
        scale = max(abs(older_mean), 1e-6)
        change = (recent_mean - older_mean) / scale
        if abs(change) < 0.10:
            return None
        return Signal(
            component_id=component_id,
            metric=metric,
            score=min(1.0, abs(change)),
            direction="up" if change > 0 else "down",
            detector="trend",
            timestamp=timestamp,
            evidence={"relative_change": round(change, 6)},
        )


class EntropyMonitor:
    """Experimental disorder signal with snapshot-idempotent history."""

    def __init__(self, window: int = 64, bins: int = 8) -> None:
        if bins < 2:
            raise ValueError("bins must be >= 2")
        self.window = window
        self.bins = bins
        self._values: MutableMapping[Tuple[str, str], Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.window)
        )
        self._history: Deque[float] = deque(maxlen=32)
        self._last_snapshot_timestamp: Optional[float] = None

    def ingest(self, sample: TelemetrySample) -> None:
        self._values[(sample.component_id, sample.metric)].append(sample.value)

    def _entropy(self, values: Sequence[float]) -> float:
        if len(values) < 4:
            return 0.0
        low, high = min(values), max(values)
        if not high > low:
            return 0.0
        width = (high - low) / self.bins
        if width <= 0.0 or not math.isfinite(width):
            return 0.0
        counts = [0] * self.bins
        for value in values:
            index = min(int((value - low) / width), self.bins - 1)
            counts[index] += 1
        total = len(values)
        entropy = 0.0
        for count in counts:
            if count:
                probability = count / total
                entropy -= probability * math.log2(probability)
        return entropy / math.log2(self.bins)

    def current_entropy(self) -> float:
        entropies = [
            self._entropy(list(values))
            for values in self._values.values()
            if len(values) >= 4
        ]
        return statistics.fmean(entropies) if entropies else 0.0

    def snapshot(self, timestamp: float) -> float:
        value = self.current_entropy()
        if self._last_snapshot_timestamp != timestamp:
            self._history.append(value)
            self._last_snapshot_timestamp = timestamp
        return value

    def entropy_acceleration(self) -> float:
        if len(self._history) < 6:
            return 0.0
        older = statistics.fmean(list(self._history)[-6:-3])
        recent = statistics.fmean(list(self._history)[-3:])
        return recent - older


class MetricRiskPolicy:
    """Conservative harmful-direction semantics for automatic risk promotion."""

    HARMFUL_UP_TOKENS = (
        "latency",
        "step_time",
        "temperature",
        "temp",
        "error",
        "ecc",
        "retry",
        "retransmit",
        "packet_loss",
        "queue_depth",
    )
    HARMFUL_DOWN_TOKENS = (
        "sm_util",
        "gpu_util",
        "utilization",
        "throughput",
        "bandwidth",
        "goodput",
        "health",
    )

    def is_harmful(self, metric: str, direction: str) -> bool:
        name = metric.lower()
        if any(token in name for token in self.HARMFUL_UP_TOKENS):
            return direction == "up"
        if any(token in name for token in self.HARMFUL_DOWN_TOKENS):
            return direction == "down"
        return False
