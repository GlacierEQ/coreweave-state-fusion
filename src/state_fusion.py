"""CoreWeave State Fusion — Unified picture from all infrastructure layers.

Their pain: Mission Control observability — understanding the full picture.

Innovation: Fuses data from GPU, network, storage, and compute layers
into a single coherent state estimate.
"""

import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class InfrastructureLayer:
    layer_name: str
    metrics: Dict[str, float]
    confidence: float
    timestamp: float
    health: str = "UNKNOWN"


class StateFusionEngine:
    def __init__(self):
        self.layers: Dict[str, InfrastructureLayer] = {}
        self._fusion_log: List[dict] = []

    def update_layer(self, layer: InfrastructureLayer):
        self.layers[layer.layer_name] = layer

    def fuse(self) -> dict:
        if not self.layers:
            return {}

        all_metrics = set()
        for layer in self.layers.values():
            all_metrics.update(layer.metrics.keys())

        fused = {}
        for metric in all_metrics:
            values = []
            weights = []
            for name, layer in self.layers.items():
                if metric in layer.metrics:
                    values.append(layer.metrics[metric])
                    weights.append(layer.confidence)

            if values:
                total = sum(weights)
                fused[metric] = round(sum(v * w for v, w in zip(values, weights)) / total, 4)

        health_scores = {"HEALTHY": 1.0, "DEGRADED": 0.5, "CRITICAL": 0.0, "UNKNOWN": 0.5}
        avg_health = sum(health_scores.get(l.health, 0.5) for l in self.layers.values()) / max(len(self.layers), 1)

        self._fusion_log.append({"timestamp": time.time(), "metrics": fused, "health": avg_health})

        return {
            "fused_metrics": fused,
            "overall_health": round(avg_health, 3),
            "layers_fused": len(self.layers),
            "layer_health": {name: layer.health for name, layer in self.layers.items()},
        }


if __name__ == "__main__":
    engine = StateFusionEngine()
    engine.update_layer(InfrastructureLayer("gpu", {"utilization": 0.75, "temperature": 72}, 0.9, time.time(), "HEALTHY"))
    engine.update_layer(InfrastructureLayer("network", {"latency_ms": 2.5, "bandwidth_gbps": 100}, 0.85, time.time(), "HEALTHY"))
    engine.update_layer(InfrastructureLayer("storage", {"iops": 50000, "throughput_gbps": 10}, 0.9, time.time(), "DEGRADED"))
    result = engine.fuse()
    print(json.dumps(result, indent=2))
