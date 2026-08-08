"""Topology-aware root-cause attribution for goodput degradation."""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import List, Tuple

from goodput_control import FusedState, Layer, TopologyGraph


@dataclass(frozen=True)
class CauseScore:
    component_id: str
    score: float
    component_risk: float
    downstream_pressure: float
    blast_radius: float
    layer: str


class RootCauseAttributor:
    """Rank likely initiating components from topology + downstream evidence.

    This is causal attribution scoring, not proof of causality. It favors
    components with persistent local risk whose dependents also show risk.
    """

    def __init__(self, minimum_component_risk: float = 0.25) -> None:
        self.minimum_component_risk = minimum_component_risk

    def rank(
        self,
        state: FusedState,
        topology: TopologyGraph,
    ) -> Tuple[CauseScore, ...]:
        active = {
            component_id: risk
            for component_id, risk in state.component_risk.items()
            if risk >= self.minimum_component_risk
        }
        if len(active) < 2:
            return ()

        total_components = max(len(topology.components), 1)
        scores: List[CauseScore] = []
        for component_id, local_risk in active.items():
            impacted = topology.blast_radius(component_id)
            downstream = [
                state.component_risk.get(other, 0.0)
                for other in impacted
                if other != component_id
            ]
            downstream_pressure = (
                statistics.fmean(downstream) if downstream else 0.0
            )
            blast = len(impacted) / total_components

            layer = topology.components[component_id].layer
            source_prior = 0.0 if layer == Layer.JOB else 0.12

            score = min(
                1.0,
                0.52 * local_risk
                + 0.24 * downstream_pressure
                + 0.12 * blast
                + source_prior,
            )
            scores.append(
                CauseScore(
                    component_id=component_id,
                    score=round(score, 6),
                    component_risk=round(local_risk, 6),
                    downstream_pressure=round(downstream_pressure, 6),
                    blast_radius=round(blast, 6),
                    layer=layer.value,
                )
            )
        return tuple(
            sorted(scores, key=lambda item: (-item.score, item.component_id))
        )
