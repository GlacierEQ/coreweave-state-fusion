"""Shared types, topology, canonical serialization, and deterministic digests."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Mapping, Optional, Set, Tuple


class Layer(str, Enum):
    JOB = "job"
    GPU = "gpu"
    NETWORK = "network"
    STORAGE = "storage"
    COMPUTE = "compute"
    SCHEDULER = "scheduler"


class Action(str, Enum):
    OBSERVE = "observe"
    THROTTLE = "throttle"
    ISOLATE_GPU = "isolate_gpu"
    DRAIN_NODE = "drain_node"
    CHECKPOINT_REQUEUE = "checkpoint_requeue"
    REROUTE = "reroute"


@dataclass(frozen=True)
class Component:
    component_id: str
    layer: Layer
    dependencies: Tuple[str, ...] = ()
    job_id: Optional[str] = None
    failure_domain: Optional[str] = None


@dataclass(frozen=True)
class TelemetrySample:
    component_id: str
    metric: str
    value: float
    timestamp: float


@dataclass(frozen=True)
class Signal:
    component_id: str
    metric: str
    score: float
    direction: str
    detector: str
    timestamp: float
    evidence: Mapping[str, float]


@dataclass(frozen=True)
class FusedState:
    observation_timestamp: float
    components: Mapping[str, Component]
    latest_metrics: Mapping[str, Mapping[str, float]]
    signals: Tuple[Signal, ...]
    layer_risk: Mapping[str, float]
    component_risk: Mapping[str, float]
    system_risk: float
    system_entropy: float
    goodput_at_risk: float


@dataclass(frozen=True)
class RemediationContext:
    confidence: float
    checkpoint_freshness: float
    replacement_capacity: float
    workload_priority: float
    recurrence_risk: float


@dataclass(frozen=True)
class ActionScore:
    action: Action
    regret: float
    lost_compute: float
    disruption: float
    false_positive: float
    recovery_latency: float
    recurrence: float
    allowed: bool
    reason: str


@dataclass(frozen=True)
class RecoveryReceipt:
    state_digest: str
    selected_action: Action
    scores: Tuple[ActionScore, ...]
    policy_reason: str
    receipt_digest: str


class TopologyGraph:
    """Deterministic workload-to-infrastructure dependency graph."""

    def __init__(self) -> None:
        self._components: dict[str, Component] = {}

    def register(self, component: Component) -> None:
        if component.component_id in self._components:
            raise ValueError(f"duplicate component: {component.component_id}")
        self._components[component.component_id] = component

    @property
    def components(self) -> Mapping[str, Component]:
        return dict(self._components)

    def validate(self) -> None:
        unknown = []
        for component in self._components.values():
            for dependency in component.dependencies:
                if dependency not in self._components:
                    unknown.append((component.component_id, dependency))
        if unknown:
            raise ValueError(f"unknown dependencies: {unknown}")

    def blast_radius(self, component_id: str) -> Set[str]:
        if component_id not in self._components:
            raise KeyError(component_id)
        impacted: Set[str] = {component_id}
        changed = True
        while changed:
            changed = False
            for component in self._components.values():
                if component.component_id in impacted:
                    continue
                if set(component.dependencies) & impacted:
                    impacted.add(component.component_id)
                    changed = True
        return impacted


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def serialize_signal(signal: Signal) -> dict:
    return {
        "component_id": signal.component_id,
        "metric": signal.metric,
        "score": signal.score,
        "direction": signal.direction,
        "detector": signal.detector,
        "timestamp": signal.timestamp,
        "evidence": dict(sorted(signal.evidence.items())),
    }


def serialize_action_score(score: ActionScore) -> dict:
    data = asdict(score)
    data["action"] = score.action.value
    if not math.isfinite(score.regret):
        data["regret"] = "INF"
    return data


def serialize_state(state: FusedState) -> dict:
    return {
        "observation_timestamp": state.observation_timestamp,
        "components": {
            key: {
                "component_id": value.component_id,
                "layer": value.layer.value,
                "dependencies": list(value.dependencies),
                "job_id": value.job_id,
                "failure_domain": value.failure_domain,
            }
            for key, value in sorted(state.components.items())
        },
        "latest_metrics": state.latest_metrics,
        "signals": [serialize_signal(signal) for signal in state.signals],
        "layer_risk": state.layer_risk,
        "component_risk": state.component_risk,
        "system_risk": state.system_risk,
        "system_entropy": state.system_entropy,
        "goodput_at_risk": state.goodput_at_risk,
    }


def digest_state(state: FusedState) -> str:
    return hashlib.sha256(
        canonical_json(serialize_state(state)).encode("utf-8")
    ).hexdigest()


def build_demo_topology() -> TopologyGraph:
    topology = TopologyGraph()
    topology.register(Component("gpu-0", Layer.GPU, failure_domain="node-0"))
    topology.register(Component("gpu-1", Layer.GPU, failure_domain="node-0"))
    topology.register(Component("nic-0", Layer.NETWORK, failure_domain="node-0"))
    topology.register(Component("storage-0", Layer.STORAGE, failure_domain="rack-a"))
    topology.register(
        Component(
            "node-0",
            Layer.COMPUTE,
            dependencies=("gpu-0", "gpu-1", "nic-0"),
            failure_domain="rack-a",
        )
    )
    topology.register(
        Component(
            "job-0",
            Layer.JOB,
            dependencies=("node-0", "storage-0"),
            job_id="job-0",
        )
    )
    topology.validate()
    return topology
