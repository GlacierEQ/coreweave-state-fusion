"""Goodput Autonomic Control Plane.

Deterministic reference implementation for topology-aware state fusion,
degradation evidence, goodput-at-risk estimation, counterfactual remediation,
and fail-closed recovery receipts.
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Deque, Dict, List, Mapping, MutableMapping, Optional, Sequence, Set, Tuple


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
    evidence: Mapping[str, float]


@dataclass(frozen=True)
class FusedState:
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
        self._components: Dict[str, Component] = {}

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


class RollingBaselineDetector:
    """Score a sample against the prior window before incorporating it."""

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
            robust_scale = max(std, max(abs(mean) * 0.01, 1e-6))
            z = (sample.value - mean) / robust_scale
            if abs(z) >= self.z_threshold:
                signal = Signal(
                    component_id=sample.component_id,
                    metric=sample.metric,
                    score=min(1.0, abs(z) / 6.0),
                    direction="up" if z > 0 else "down",
                    detector="rolling_z",
                    evidence={
                        "z": round(z, 6),
                        "baseline_mean": round(mean, 6),
                        "baseline_std": round(std, 6),
                    },
                )
        values.append(sample.value)
        return signal

    def trend_signal(self, component_id: str, metric: str, span: int = 8) -> Optional[Signal]:
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
            evidence={"relative_change": round(change, 6)},
        )


class EntropyMonitor:
    """Experimental disorder signal to benchmark, not a failure-prediction claim."""

    def __init__(self, window: int = 64, bins: int = 8) -> None:
        self.window = window
        self.bins = bins
        self._values: MutableMapping[Tuple[str, str], Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.window)
        )
        self._history: Deque[float] = deque(maxlen=32)

    def ingest(self, sample: TelemetrySample) -> None:
        self._values[(sample.component_id, sample.metric)].append(sample.value)

    def _entropy(self, values: Sequence[float]) -> float:
        if len(values) < 4:
            return 0.0
        low, high = min(values), max(values)
        if math.isclose(low, high, rel_tol=0.0, abs_tol=1e-12):
            return 0.0
        counts = [0] * self.bins
        width = (high - low) / self.bins
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

    def system_entropy(self) -> float:
        entropies = [
            self._entropy(list(values))
            for values in self._values.values()
            if len(values) >= 4
        ]
        value = statistics.fmean(entropies) if entropies else 0.0
        self._history.append(value)
        return value

    def entropy_acceleration(self) -> float:
        if len(self._history) < 6:
            return 0.0
        older = statistics.fmean(list(self._history)[-6:-3])
        recent = statistics.fmean(list(self._history)[-3:])
        return recent - older


class GoodputModel:
    """Transparent heuristic for useful-work risk; calibrate with trace evidence."""

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
    def __init__(self, topology: TopologyGraph) -> None:
        topology.validate()
        self.topology = topology
        self.baseline = RollingBaselineDetector()
        self.entropy = EntropyMonitor()
        self.latest: MutableMapping[str, Dict[str, float]] = defaultdict(dict)
        self.signals: List[Signal] = []

    def ingest(self, sample: TelemetrySample) -> Optional[Signal]:
        if sample.component_id not in self.topology.components:
            raise KeyError(f"unknown component: {sample.component_id}")
        self.latest[sample.component_id][sample.metric] = sample.value
        signal = self.baseline.ingest(sample)
        self.entropy.ingest(sample)
        if signal:
            self.signals.append(signal)
        return signal

    def add_trend_signals(self) -> None:
        for component_id, metrics in self.latest.items():
            for metric in metrics:
                signal = self.baseline.trend_signal(component_id, metric)
                if signal:
                    self.signals.append(signal)

    def fuse(self) -> FusedState:
        self.add_trend_signals()
        component_risk: Dict[str, float] = {}
        for component_id in self.latest:
            scores = sorted(
                (s.score for s in self.signals if s.component_id == component_id),
                reverse=True,
            )
            if len(scores) < 3:
                risk = 0.0
            else:
                risk = statistics.fmean(scores[: min(5, len(scores))])
            component_risk[component_id] = round(risk, 6)

        layer_scores: MutableMapping[str, List[float]] = defaultdict(list)
        for component_id, risk in component_risk.items():
            layer = self.topology.components[component_id].layer.value
            layer_scores[layer].append(risk)
        layer_risk = {
            layer: round(statistics.fmean(values), 6)
            for layer, values in sorted(layer_scores.items())
        }

        entropy = self.entropy.system_entropy()
        entropy_accel = max(0.0, self.entropy.entropy_acceleration())
        max_component = max(component_risk.values(), default=0.0)
        cross_layer_pressure = statistics.fmean(layer_risk.values()) if layer_risk else 0.0
        system_risk = min(
            1.0,
            0.55 * max_component
            + 0.30 * cross_layer_pressure
            + 0.15 * min(1.0, entropy_accel * 3.0),
        )
        goodput_at_risk = GoodputModel.estimate(component_risk, self.topology)
        return FusedState(
            components=self.topology.components,
            latest_metrics={k: dict(sorted(v.items())) for k, v in sorted(self.latest.items())},
            signals=tuple(self.signals),
            layer_risk=layer_risk,
            component_risk=dict(sorted(component_risk.items())),
            system_risk=round(system_risk, 6),
            system_entropy=round(entropy, 6),
            goodput_at_risk=goodput_at_risk,
        )


class RecoveryPolicy:
    DISRUPTIVE = {
        Action.ISOLATE_GPU,
        Action.DRAIN_NODE,
        Action.CHECKPOINT_REQUEUE,
        Action.REROUTE,
    }

    def __init__(self, minimum_confidence: float = 0.65, minimum_replacement_capacity: float = 0.20) -> None:
        self.minimum_confidence = minimum_confidence
        self.minimum_replacement_capacity = minimum_replacement_capacity

    def allowed(self, action: Action, context: RemediationContext) -> Tuple[bool, str]:
        if action not in self.DISRUPTIVE:
            return True, "non-disruptive action"
        if context.confidence < self.minimum_confidence:
            return False, "fail-closed: insufficient fault confidence"
        if action == Action.REROUTE and context.replacement_capacity < self.minimum_replacement_capacity:
            return False, "fail-closed: insufficient replacement capacity"
        if action == Action.CHECKPOINT_REQUEUE and context.checkpoint_freshness < 0.25:
            return False, "fail-closed: checkpoint too stale"
        return True, "policy conditions satisfied"


class CounterfactualPlanner:
    """Rank interventions by Recovery Regret."""

    BASE = {
        Action.OBSERVE: (0.92, 0.01, 0.00, 0.90, 0.90),
        Action.THROTTLE: (0.70, 0.10, 0.05, 0.45, 0.65),
        Action.ISOLATE_GPU: (0.34, 0.28, 0.16, 0.30, 0.25),
        Action.DRAIN_NODE: (0.24, 0.48, 0.24, 0.42, 0.20),
        Action.CHECKPOINT_REQUEUE: (0.18, 0.55, 0.20, 0.52, 0.16),
        Action.REROUTE: (0.14, 0.42, 0.18, 0.34, 0.18),
    }

    def __init__(self, policy: Optional[RecoveryPolicy] = None) -> None:
        self.policy = policy or RecoveryPolicy()

    def _score(self, action: Action, state: FusedState, context: RemediationContext) -> ActionScore:
        lost_factor, disruption, fp_factor, latency, recurrence_factor = self.BASE[action]
        risk = state.goodput_at_risk
        confidence = min(max(context.confidence, 0.0), 1.0)
        lost_compute = risk * lost_factor
        disruption_cost = disruption * (0.45 + 0.55 * context.workload_priority)
        false_positive = fp_factor * (1.0 - confidence)
        if action == Action.CHECKPOINT_REQUEUE:
            disruption_cost *= 1.25 - 0.50 * context.checkpoint_freshness
        if action == Action.REROUTE:
            disruption_cost *= 1.25 - 0.50 * context.replacement_capacity
        recovery_latency = latency * (0.35 + 0.65 * risk)
        recurrence = recurrence_factor * context.recurrence_risk
        regret = (
            0.38 * lost_compute
            + 0.22 * disruption_cost
            + 0.16 * false_positive
            + 0.12 * recovery_latency
            + 0.12 * recurrence
        )
        allowed, reason = self.policy.allowed(action, context)
        if not allowed:
            regret = float("inf")
        return ActionScore(
            action=action,
            regret=round(regret, 6) if math.isfinite(regret) else regret,
            lost_compute=round(lost_compute, 6),
            disruption=round(disruption_cost, 6),
            false_positive=round(false_positive, 6),
            recovery_latency=round(recovery_latency, 6),
            recurrence=round(recurrence, 6),
            allowed=allowed,
            reason=reason,
        )

    def rank(self, state: FusedState, context: RemediationContext) -> Tuple[ActionScore, ...]:
        scores = [self._score(action, state, context) for action in Action]
        return tuple(sorted(scores, key=lambda score: (score.regret, list(Action).index(score.action))))

    def choose(self, state: FusedState, context: RemediationContext) -> RecoveryReceipt:
        scores = self.rank(state, context)
        allowed = [score for score in scores if score.allowed]
        selected = allowed[0] if allowed else next(s for s in scores if s.action == Action.OBSERVE)
        policy_reason = selected.reason
        active_components = sum(risk >= 0.25 for risk in state.component_risk.values())
        if active_components < 2 or state.system_risk < 0.25 or state.goodput_at_risk < 0.25:
            selected = next(s for s in scores if s.action == Action.OBSERVE)
            policy_reason = "observe: insufficient cross-layer persistent measured goodput risk"
        state_digest = digest_state(state)
        payload = {
            "state_digest": state_digest,
            "selected_action": selected.action.value,
            "scores": [serialize_action_score(score) for score in scores],
            "policy_reason": policy_reason,
        }
        receipt_digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        return RecoveryReceipt(
            state_digest=state_digest,
            selected_action=selected.action,
            scores=scores,
            policy_reason=policy_reason,
            receipt_digest=receipt_digest,
        )


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def serialize_signal(signal: Signal) -> dict:
    return {
        "component_id": signal.component_id,
        "metric": signal.metric,
        "score": signal.score,
        "direction": signal.direction,
        "detector": signal.detector,
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
    return hashlib.sha256(canonical_json(serialize_state(state)).encode("utf-8")).hexdigest()


def build_demo_topology() -> TopologyGraph:
    topology = TopologyGraph()
    topology.register(Component("gpu-0", Layer.GPU, failure_domain="node-0"))
    topology.register(Component("gpu-1", Layer.GPU, failure_domain="node-0"))
    topology.register(Component("nic-0", Layer.NETWORK, failure_domain="node-0"))
    topology.register(Component("storage-0", Layer.STORAGE, failure_domain="rack-a"))
    topology.register(Component("node-0", Layer.COMPUTE, dependencies=("gpu-0", "gpu-1", "nic-0"), failure_domain="rack-a"))
    topology.register(Component("job-0", Layer.JOB, dependencies=("node-0", "storage-0"), job_id="job-0"))
    topology.validate()
    return topology
