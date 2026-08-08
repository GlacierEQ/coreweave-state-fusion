"""Bounded cross-layer fusion and transparent goodput risk estimation."""
from __future__ import annotations

import math
import statistics
from collections import defaultdict
from typing import Dict, List, Mapping, MutableMapping, Optional

from control_types import FusedState, Signal, TelemetrySample, TopologyGraph
from detectors import EntropyMonitor, MetricRiskPolicy, RollingBaselineDetector


class GoodputModel:
    """Map current degradation to an estimated fraction of useful work at risk."""

    @staticmethod
    def estimate(component_risk: Mapping[str, float], topology: TopologyGraph) -> float:
        if not component_risk:
            return 0.0
        weighted_losses: List[float] = []
        component_count = max(len(topology.components), 1)
        for component_id, risk in component_risk.items():
            blast = len(topology.blast_radius(component_id)) / component_count
            weighted_losses.append(min(1.0, risk * (0.55 + 0.45 * blast)))
        survival = 1.0
        for loss in weighted_losses:
            survival *= 1.0 - min(max(loss, 0.0), 0.95)
        return round(1.0 - survival, 6)


class StateFusionEngine:
    """Fuse bounded current evidence into an idempotent cross-layer snapshot."""

    def __init__(
        self,
        topology: TopologyGraph,
        evidence_ttl: float = 16.0,
        metric_policy: Optional[MetricRiskPolicy] = None,
    ) -> None:
        topology.validate()
        if evidence_ttl <= 0:
            raise ValueError("evidence_ttl must be positive")
        self.topology = topology
        self.baseline = RollingBaselineDetector()
        self.entropy = EntropyMonitor()
        self.metric_policy = metric_policy or MetricRiskPolicy()
        self.evidence_ttl = evidence_ttl
        self.latest: MutableMapping[str, Dict[str, float]] = defaultdict(dict)
        self.signals: List[Signal] = []
        self._latest_timestamp = 0.0

    def _prune_signals(self, timestamp: float) -> None:
        cutoff = timestamp - self.evidence_ttl
        self.signals = [signal for signal in self.signals if signal.timestamp >= cutoff]

    def ingest(self, sample: TelemetrySample) -> Optional[Signal]:
        if sample.component_id not in self.topology.components:
            raise KeyError(f"unknown component: {sample.component_id}")
        if not sample.metric:
            raise ValueError("metric must be non-empty")
        if not math.isfinite(sample.value) or not math.isfinite(sample.timestamp):
            raise ValueError("telemetry value and timestamp must be finite")
        if sample.timestamp < self._latest_timestamp:
            raise ValueError("telemetry timestamps must be non-decreasing")

        self._latest_timestamp = sample.timestamp
        self.latest[sample.component_id][sample.metric] = sample.value
        signal = self.baseline.ingest(sample)
        self.entropy.ingest(sample)
        if signal:
            self.signals.append(signal)
        self._prune_signals(sample.timestamp)
        return signal

    def _trend_signals(self) -> List[Signal]:
        trends: List[Signal] = []
        for component_id, metrics in self.latest.items():
            for metric in metrics:
                signal = self.baseline.trend_signal(
                    component_id,
                    metric,
                    timestamp=self._latest_timestamp,
                )
                if signal:
                    trends.append(signal)
        return trends

    def fuse(self) -> FusedState:
        active_signals = sorted(
            [*self.signals, *self._trend_signals()],
            key=lambda signal: (
                signal.timestamp,
                signal.component_id,
                signal.metric,
                signal.detector,
                signal.direction,
            ),
        )

        component_risk: Dict[str, float] = {}
        for component_id in self.latest:
            scores = sorted(
                (
                    signal.score
                    for signal in active_signals
                    if signal.component_id == component_id
                    and self.metric_policy.is_harmful(signal.metric, signal.direction)
                ),
                reverse=True,
            )
            risk = 0.0 if len(scores) < 3 else statistics.fmean(scores[:5])
            component_risk[component_id] = round(risk, 6)

        layer_scores: MutableMapping[str, List[float]] = defaultdict(list)
        for component_id, risk in component_risk.items():
            layer = self.topology.components[component_id].layer.value
            layer_scores[layer].append(risk)
        layer_risk = {
            layer: round(statistics.fmean(values), 6)
            for layer, values in sorted(layer_scores.items())
        }

        entropy = self.entropy.snapshot(self._latest_timestamp)
        entropy_accel = max(0.0, self.entropy.entropy_acceleration())
        max_component = max(component_risk.values(), default=0.0)
        cross_layer_pressure = (
            statistics.fmean(layer_risk.values()) if layer_risk else 0.0
        )
        system_risk = min(
            1.0,
            0.55 * max_component
            + 0.30 * cross_layer_pressure
            + 0.15 * min(1.0, entropy_accel * 3.0),
        )
        return FusedState(
            observation_timestamp=self._latest_timestamp,
            components=self.topology.components,
            latest_metrics={
                key: dict(sorted(value.items()))
                for key, value in sorted(self.latest.items())
            },
            signals=tuple(active_signals),
            layer_risk=layer_risk,
            component_risk=dict(sorted(component_risk.items())),
            system_risk=round(system_risk, 6),
            system_entropy=round(entropy, 6),
            goodput_at_risk=GoodputModel.estimate(component_risk, self.topology),
        )
