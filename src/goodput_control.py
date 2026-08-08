"""Public compatibility surface for the Goodput Autonomic Control Plane.

The implementation is split by responsibility so detection evidence, fusion,
and recovery policy can evolve independently while preserving the original
module imports used by the failure lab and evidence tooling.
"""
from control_types import (
    Action,
    ActionScore,
    Component,
    FusedState,
    Layer,
    RecoveryReceipt,
    RemediationContext,
    Signal,
    TelemetrySample,
    TopologyGraph,
    build_demo_topology,
    canonical_json,
    digest_state,
    serialize_action_score,
    serialize_signal,
    serialize_state,
)
from detectors import EntropyMonitor, MetricRiskPolicy, RollingBaselineDetector
from fusion_engine import GoodputModel, StateFusionEngine
from recovery import CounterfactualPlanner, RecoveryPolicy

__all__ = [
    "Action",
    "ActionScore",
    "Component",
    "CounterfactualPlanner",
    "EntropyMonitor",
    "FusedState",
    "GoodputModel",
    "Layer",
    "MetricRiskPolicy",
    "RecoveryPolicy",
    "RecoveryReceipt",
    "RemediationContext",
    "RollingBaselineDetector",
    "Signal",
    "StateFusionEngine",
    "TelemetrySample",
    "TopologyGraph",
    "build_demo_topology",
    "canonical_json",
    "digest_state",
    "serialize_action_score",
    "serialize_signal",
    "serialize_state",
]
