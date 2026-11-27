"""Freshness-aware state fusion for heterogeneous infrastructure telemetry.

This private prototype combines overlapping metrics using explicit confidence
weights and rejects stale observations. It does not claim production CoreWeave
behavior, deployment, or measured reliability impact.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InfrastructureLayer:
    layer_name: str
    metrics: dict[str, float]
    confidence: float
    timestamp: float
    health: str = "UNKNOWN"


class StateFusionEngine:
    HEALTH_SCORES = {
        "HEALTHY": 1.0,
        "DEGRADED": 0.5,
        "CRITICAL": 0.0,
        "UNKNOWN": 0.5,
    }

    def __init__(self, *, max_age_s: float = 60.0) -> None:
        if max_age_s <= 0:
            raise ValueError("max_age_s must be positive")
        self.max_age_s = max_age_s
        self.layers: dict[str, InfrastructureLayer] = {}
        self._fusion_log: list[dict[str, object]] = []

    def update_layer(self, layer: InfrastructureLayer) -> None:
        if not layer.layer_name:
            raise ValueError("layer_name is required")
        if not 0.0 <= layer.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        self.layers[layer.layer_name] = layer

    def _fresh_layers(
        self,
        now: float,
    ) -> tuple[dict[str, InfrastructureLayer], list[str]]:
        fresh: dict[str, InfrastructureLayer] = {}
        stale: list[str] = []
        for name, layer in self.layers.items():
            age = max(0.0, now - layer.timestamp)
            if age <= self.max_age_s:
                fresh[name] = layer
            else:
                stale.append(name)
        return fresh, sorted(stale)

    def fuse(self, *, now: float | None = None) -> dict[str, object]:
        current_time = time.time() if now is None else now
        fresh, stale = self._fresh_layers(current_time)
        if not fresh:
            return {
                "fused_metrics": {},
                "overall_health": None,
                "layers_fused": 0,
                "stale_layers": stale,
                "unresolved_metrics": [],
                "metric_provenance": {},
            }

        metric_names = sorted(
            {
                metric
                for layer in fresh.values()
                for metric in layer.metrics
            }
        )
        fused: dict[str, float] = {}
        unresolved: list[str] = []
        provenance: dict[str, list[dict[str, object]]] = {}

        for metric in metric_names:
            contributors: list[tuple[str, float, float]] = []
            for name, layer in fresh.items():
                if metric in layer.metrics:
                    contributors.append(
                        (name, layer.metrics[metric], layer.confidence)
                    )
            total_weight = sum(weight for _, _, weight in contributors)
            provenance[metric] = [
                {
                    "layer": name,
                    "value": value,
                    "confidence": weight,
                }
                for name, value, weight in contributors
            ]
            if total_weight <= 0.0:
                unresolved.append(metric)
                continue
            fused[metric] = round(
                sum(value * weight for _, value, weight in contributors)
                / total_weight,
                4,
            )

        health_weight = sum(layer.confidence for layer in fresh.values())
        overall_health: float | None
        if health_weight <= 0.0:
            overall_health = None
        else:
            overall_health = round(
                sum(
                    self.HEALTH_SCORES.get(layer.health, 0.5)
                    * layer.confidence
                    for layer in fresh.values()
                )
                / health_weight,
                3,
            )

        result: dict[str, object] = {
            "fused_metrics": fused,
            "overall_health": overall_health,
            "layers_fused": len(fresh),
            "layer_health": {
                name: layer.health for name, layer in sorted(fresh.items())
            },
            "stale_layers": stale,
            "unresolved_metrics": sorted(unresolved),
            "metric_provenance": provenance,
        }
        self._fusion_log.append(
            {
                "timestamp": current_time,
                "layers_fused": len(fresh),
                "stale_layers": stale,
                "unresolved_metrics": sorted(unresolved),
            }
        )
        return result


if __name__ == "__main__":
    demo_now = 1_000_000.0
    engine = StateFusionEngine(max_age_s=60.0)
    engine.update_layer(
        InfrastructureLayer(
            "gpu-observer-a",
            {"utilization": 0.75, "temperature": 72.0},
            0.9,
            demo_now - 5,
            "HEALTHY",
        )
    )
    engine.update_layer(
        InfrastructureLayer(
            "gpu-observer-b",
            {"utilization": 0.81, "temperature": 74.0},
            0.6,
            demo_now - 10,
            "DEGRADED",
        )
    )
    print(json.dumps(engine.fuse(now=demo_now), indent=2))
