"""Fail-closed recovery policy and Recovery Regret planning."""
from __future__ import annotations

import hashlib
import math
from typing import Optional, Tuple

from control_types import (
    Action,
    ActionScore,
    FusedState,
    RecoveryReceipt,
    RemediationContext,
    canonical_json,
    digest_state,
    serialize_action_score,
)


class RecoveryPolicy:
    DISRUPTIVE = {
        Action.ISOLATE_GPU,
        Action.DRAIN_NODE,
        Action.CHECKPOINT_REQUEUE,
        Action.REROUTE,
    }

    def __init__(
        self,
        minimum_confidence: float = 0.65,
        minimum_replacement_capacity: float = 0.20,
    ) -> None:
        self.minimum_confidence = minimum_confidence
        self.minimum_replacement_capacity = minimum_replacement_capacity

    def allowed(self, action: Action, context: RemediationContext) -> Tuple[bool, str]:
        if action not in self.DISRUPTIVE:
            return True, "non-disruptive action"
        if context.confidence < self.minimum_confidence:
            return False, "fail-closed: insufficient fault confidence"
        if (
            action == Action.REROUTE
            and context.replacement_capacity < self.minimum_replacement_capacity
        ):
            return False, "fail-closed: insufficient replacement capacity"
        if (
            action == Action.CHECKPOINT_REQUEUE
            and context.checkpoint_freshness < 0.25
        ):
            return False, "fail-closed: checkpoint too stale"
        return True, "policy conditions satisfied"


class CounterfactualPlanner:
    """Rank interventions by expected Recovery Regret."""

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

    def _score(
        self,
        action: Action,
        state: FusedState,
        context: RemediationContext,
    ) -> ActionScore:
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

    def rank(
        self,
        state: FusedState,
        context: RemediationContext,
    ) -> Tuple[ActionScore, ...]:
        scores = [self._score(action, state, context) for action in Action]
        return tuple(
            sorted(
                scores,
                key=lambda score: (score.regret, list(Action).index(score.action)),
            )
        )

    def choose(self, state: FusedState, context: RemediationContext) -> RecoveryReceipt:
        scores = self.rank(state, context)
        allowed = [score for score in scores if score.allowed]
        selected = allowed[0] if allowed else next(
            score for score in scores if score.action == Action.OBSERVE
        )
        policy_reason = selected.reason
        active_components = sum(
            risk >= 0.25 for risk in state.component_risk.values()
        )
        if (
            active_components < 2
            or state.system_risk < 0.25
            or state.goodput_at_risk < 0.25
        ):
            selected = next(
                score for score in scores if score.action == Action.OBSERVE
            )
            policy_reason = (
                "observe: insufficient cross-layer persistent measured goodput risk"
            )

        state_digest = digest_state(state)
        payload = {
            "state_digest": state_digest,
            "selected_action": selected.action.value,
            "scores": [serialize_action_score(score) for score in scores],
            "policy_reason": policy_reason,
        }
        receipt_digest = hashlib.sha256(
            canonical_json(payload).encode("utf-8")
        ).hexdigest()
        return RecoveryReceipt(
            state_digest=state_digest,
            selected_action=selected.action,
            scores=scores,
            policy_reason=policy_reason,
            receipt_digest=receipt_digest,
        )
