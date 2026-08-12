"""Freshness-aware infrastructure state fusion.

The engine combines heterogeneous infrastructure observations without pretending
that stale telemetry has the same evidentiary value as fresh telemetry.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

HEALTH_SCORES = {
    "HEALTHY": 1.0,
    "DEGRADED": 0.5,
    "CRITICAL": 0.0,
    "UNKNOWN": 0.25,
}


@dataclass(frozen=True)
class InfrastructureLayer:
    layer_name: str
    metrics: dict[str, float]
    confidence: float
    timestamp: float
    health: str = "UNKNOWN"

    def __post_init__(self) -> None:
        if not self.layer_name.strip():
            raise ValueError("layer_name is required")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not math.isfinite(self.timestamp):
            raise ValueError("timestamp must be finite")
        normalized_health = self.health.upper()
        if normalized_health not in HEALTH_SCORES:
            raise ValueError(f"unsupported health state: {self.health}")
        object.__setattr__(self, "health", normalized_health)

        normalized: dict[str, float] = {}
        for name, value in self.metrics.items():
            if not str(name).strip():
                raise ValueError("metric names must be non-empty")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError(f"metric {name!r} must be finite")
            normalized[str(name)] = number
        object.__setattr__(self, "metrics", normalized)


class StateFusionEngine:
    """Fuse fresh layer observations with confidence and age-aware weighting."""

    def __init__(
        self,
        *,
        freshness_half_life_s: float = 60.0,
        max_age_s: float = 300.0,
    ) -> None:
        if freshness_half_life_s <= 0:
            raise ValueError("freshness_half_life_s must be positive")
        if max_age_s < 0:
            raise ValueError("max_age_s must be >= 0")
        self.freshness_half_life_s = freshness_half_life_s
        self.max_age_s = max_age_s
        self.layers: dict[str, InfrastructureLayer] = {}
        self._fusion_log: list[dict[str, Any]] = []

    def update_layer(self, layer: InfrastructureLayer) -> None:
        previous = self.layers.get(layer.layer_name)
        if previous is not None and layer.timestamp < previous.timestamp:
            raise ValueError(
                f"out-of-order observation for {layer.layer_name}: "
                f"{layer.timestamp} < {previous.timestamp}"
            )
        self.layers[layer.layer_name] = layer

    def _age(self, layer: InfrastructureLayer, now: float) -> float:
        return max(0.0, now - layer.timestamp)

    def _effective_weight(self, layer: InfrastructureLayer, now: float) -> float:
        age = self._age(layer, now)
        if age > self.max_age_s:
            return 0.0
        freshness = 0.5 ** (age / self.freshness_half_life_s)
        return layer.confidence * freshness

    def fuse(self, *, now: float | None = None) -> dict[str, Any]:
        current = time.time() if now is None else float(now)
        if not math.isfinite(current):
            raise ValueError("now must be finite")
        if not self.layers:
            return {
                "fused_metrics": {},
                "overall_health": None,
                "layers_observed": 0,
                "layers_used": 0,
                "stale_layers": [],
                "zero_weight_layers": [],
                "layer_health": {},
                "metric_evidence": {},
            }

        weights = {
            name: self._effective_weight(layer, current)
            for name, layer in self.layers.items()
        }
        stale_layers = sorted(
            name
            for name, layer in self.layers.items()
            if self._age(layer, current) > self.max_age_s
        )
        zero_weight_layers = sorted(
            name
            for name, layer in self.layers.items()
            if name not in stale_layers and layer.confidence == 0.0
        )

        all_metrics = sorted(
            {metric for layer in self.layers.values() for metric in layer.metrics}
        )
        fused_metrics: dict[str, float] = {}
        metric_evidence: dict[str, dict[str, Any]] = {}

        for metric in all_metrics:
            contributors: list[dict[str, Any]] = []
            numerator = 0.0
            denominator = 0.0
            for name, layer in sorted(self.layers.items()):
                if metric not in layer.metrics:
                    continue
                weight = weights[name]
                contributors.append(
                    {
                        "layer": name,
                        "value": layer.metrics[metric],
                        "confidence": layer.confidence,
                        "age_s": round(self._age(layer, current), 6),
                        "effective_weight": round(weight, 9),
                        "used": weight > 0,
                    }
                )
                if weight > 0:
                    numerator += layer.metrics[metric] * weight
                    denominator += weight

            if denominator > 0:
                fused_metrics[metric] = round(numerator / denominator, 6)
            metric_evidence[metric] = {
                "resolved": denominator > 0,
                "effective_weight_sum": round(denominator, 9),
                "contributors": contributors,
            }

        active = [
            (name, layer, weights[name])
            for name, layer in sorted(self.layers.items())
            if weights[name] > 0
        ]
        health_denominator = sum(weight for _, _, weight in active)
        overall_health = None
        if health_denominator > 0:
            health_numerator = sum(
                HEALTH_SCORES[layer.health] * weight for _, layer, weight in active
            )
            overall_health = round(health_numerator / health_denominator, 6)

        result = {
            "fused_metrics": fused_metrics,
            "overall_health": overall_health,
            "layers_observed": len(self.layers),
            "layers_used": len(active),
            "stale_layers": stale_layers,
            "zero_weight_layers": zero_weight_layers,
            "layer_health": {
                name: {
                    "health": layer.health,
                    "confidence": layer.confidence,
                    "age_s": round(self._age(layer, current), 6),
                    "effective_weight": round(weights[name], 9),
                }
                for name, layer in sorted(self.layers.items())
            },
            "metric_evidence": metric_evidence,
        }
        self._fusion_log.append({"timestamp": current, **result})
        return result

    @property
    def fusion_log(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._fusion_log)


def layer_from_dict(payload: dict[str, Any]) -> InfrastructureLayer:
    return InfrastructureLayer(
        layer_name=str(payload["layer_name"]),
        metrics={str(k): float(v) for k, v in dict(payload["metrics"]).items()},
        confidence=float(payload["confidence"]),
        timestamp=float(payload["timestamp"]),
        health=str(payload.get("health", "UNKNOWN")),
    )


def run_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    engine = StateFusionEngine(
        freshness_half_life_s=float(payload.get("freshness_half_life_s", 60.0)),
        max_age_s=float(payload.get("max_age_s", 300.0)),
    )
    layers = payload.get("layers")
    if not isinstance(layers, list):
        raise ValueError("layers must be a JSON array")
    for raw in layers:
        if not isinstance(raw, dict):
            raise ValueError("each layer must be a JSON object")
        engine.update_layer(layer_from_dict(raw))
    return engine.fuse(now=float(payload.get("now", time.time())))


def demo() -> dict[str, Any]:
    return run_snapshot(
        {
            "now": 1000.0,
            "freshness_half_life_s": 60.0,
            "max_age_s": 180.0,
            "layers": [
                {
                    "layer_name": "gpu",
                    "metrics": {"pressure": 0.82, "temperature_c": 72},
                    "confidence": 0.95,
                    "timestamp": 995.0,
                    "health": "HEALTHY",
                },
                {
                    "layer_name": "scheduler",
                    "metrics": {"pressure": 0.55, "queue_depth": 18},
                    "confidence": 0.85,
                    "timestamp": 940.0,
                    "health": "DEGRADED",
                },
                {
                    "layer_name": "storage-stale",
                    "metrics": {"pressure": 0.1, "iops": 50000},
                    "confidence": 1.0,
                    "timestamp": 700.0,
                    "health": "HEALTHY",
                },
            ],
        }
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freshness-aware infrastructure state fusion")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("demo", help="Run a deterministic fusion demonstration")
    fuse = subparsers.add_parser("fuse", help="Fuse a JSON infrastructure snapshot")
    fuse.add_argument("--input", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "demo":
        result = demo()
    else:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("input must be a JSON object")
        result = run_snapshot(payload)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["layers_used"] > 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
