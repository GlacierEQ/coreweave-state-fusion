"""Deterministic failure lab for the Goodput Autonomic Control Plane."""
from __future__ import annotations

import argparse
import json
import random
import sys
from dataclasses import replace
from itertools import groupby
from pathlib import Path
from typing import Dict, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from attribution import RootCauseAttributor  # noqa: E402
from calibration import SyntheticGoodputCalibrator  # noqa: E402
from goodput_control import (  # noqa: E402
    CounterfactualPlanner,
    RemediationContext,
    StateFusionEngine,
    TelemetrySample,
    build_demo_topology,
    serialize_action_score,
    serialize_state,
)


def generate_samples(
    seed: int,
    steps: int = 48,
    fault_at: int = 32,
    fault: str = "network_straggler",
) -> Iterable[TelemetrySample]:
    rng = random.Random(seed)
    timestamp = 0.0
    for step in range(steps):
        timestamp += 1.0
        gpu0 = 0.91 + rng.gauss(0, 0.012)
        gpu1 = 0.90 + rng.gauss(0, 0.012)
        nic_latency = 2.0 + rng.gauss(0, 0.08)
        storage_latency = 4.0 + rng.gauss(0, 0.15)
        step_time = 1.0 + rng.gauss(0, 0.015)

        if step >= fault_at:
            age = step - fault_at + 1
            if fault == "network_straggler":
                nic_latency += 0.55 * age
                gpu1 -= min(0.45, 0.015 * age)
                step_time += 0.12 * age
            elif fault == "gpu_thermal_drift":
                gpu1 -= min(0.50, 0.02 * age)
                step_time += 0.09 * age
            elif fault == "storage_degradation":
                storage_latency += 0.9 * age
                step_time += 0.07 * age
            elif fault == "healthy":
                pass
            else:
                raise ValueError(f"unknown fault: {fault}")

        yield TelemetrySample("gpu-0", "sm_util", gpu0, timestamp)
        yield TelemetrySample("gpu-1", "sm_util", gpu1, timestamp)
        yield TelemetrySample("nic-0", "latency_ms", nic_latency, timestamp)
        yield TelemetrySample("storage-0", "latency_ms", storage_latency, timestamp)
        yield TelemetrySample("job-0", "step_time_s", step_time, timestamp)


def _is_actionable(state) -> bool:
    active_components = sum(
        risk >= 0.25 for risk in state.component_risk.values()
    )
    return (
        active_components >= 2
        and state.system_risk >= 0.25
        and state.goodput_at_risk >= 0.25
    )


def run_scenario(seed: int, fault: str) -> Dict[str, object]:
    topology = build_demo_topology()
    engine = StateFusionEngine(topology)
    calibrator = SyntheticGoodputCalibrator()
    first_raw_signal = None
    raw_signal_count = 0
    background_raw_signals = 0
    first_actionable = None
    first_post_injection_actionable = None
    actionable_false_positive = False
    sample_index = 0
    pre_fault_step_times = []
    post_fault_step_times = []
    fault_injection_timestamp = 33.0 if fault != "healthy" else None
    raw_state = None
    state = None

    stream = generate_samples(seed=seed, fault=fault)
    for timestamp, step_samples in groupby(stream, key=lambda sample: sample.timestamp):
        for sample in step_samples:
            signal = engine.ingest(sample)
            if signal:
                raw_signal_count += 1
                if first_raw_signal is None:
                    first_raw_signal = sample.timestamp
                if (
                    fault_injection_timestamp is None
                    or sample.timestamp < fault_injection_timestamp
                ):
                    background_raw_signals += 1
            if sample.component_id == "job-0" and sample.metric == "step_time_s":
                if sample.timestamp <= 32:
                    pre_fault_step_times.append(sample.value)
                else:
                    post_fault_step_times.append(sample.value)
            sample_index += 1

        raw_state = engine.fuse()
        state = replace(
            raw_state,
            goodput_at_risk=calibrator.apply(raw_state.goodput_at_risk),
        )
        if _is_actionable(state):
            if first_actionable is None:
                first_actionable = timestamp
            if fault_injection_timestamp is None:
                actionable_false_positive = True
            elif timestamp < fault_injection_timestamp:
                actionable_false_positive = True
            elif first_post_injection_actionable is None:
                first_post_injection_actionable = timestamp

    if raw_state is None or state is None:
        raise RuntimeError("scenario produced no telemetry")

    attributor = RootCauseAttributor()
    causes = attributor.rank(state, topology)
    planner = CounterfactualPlanner()
    context = RemediationContext(
        confidence=min(1.0, 0.55 + state.system_risk),
        checkpoint_freshness=0.85,
        replacement_capacity=0.70,
        workload_priority=0.90,
        recurrence_risk=0.65,
    )
    receipt = planner.choose(state, context)

    baseline_step = sum(pre_fault_step_times) / max(len(pre_fault_step_times), 1)
    post_fault_step = sum(post_fault_step_times) / max(len(post_fault_step_times), 1)
    actual_goodput_loss = (
        max(0.0, 1.0 - baseline_step / post_fault_step)
        if post_fault_step > 0
        else 0.0
    )
    expected_root = {
        "network_straggler": "nic-0",
        "gpu_thermal_drift": "gpu-1",
        "storage_degradation": "storage-0",
        "healthy": None,
    }[fault]
    top_cause = causes[0].component_id if causes else None
    actionable_detection = (
        first_post_injection_actionable is not None
        if fault_injection_timestamp is not None
        else False
    )
    detection_delay_steps = (
        first_post_injection_actionable - fault_injection_timestamp
        if first_post_injection_actionable is not None
        and fault_injection_timestamp is not None
        else None
    )

    return {
        "seed": seed,
        "fault": fault,
        "fault_injection_timestamp": fault_injection_timestamp,
        "expected_root": expected_root,
        "top_cause": top_cause,
        "top1_correct": top_cause == expected_root if expected_root else top_cause is None,
        "causes": [
            {
                "component_id": cause.component_id,
                "score": cause.score,
                "component_risk": cause.component_risk,
                "downstream_pressure": cause.downstream_pressure,
                "blast_radius": cause.blast_radius,
                "layer": cause.layer,
            }
            for cause in causes
        ],
        "first_raw_signal_timestamp": first_raw_signal,
        "raw_signal_observed": first_raw_signal is not None,
        "raw_signal_count": raw_signal_count,
        "background_raw_signals": background_raw_signals,
        "first_actionable_timestamp": first_actionable,
        "first_actionable_detection_timestamp": first_post_injection_actionable,
        "actionable_detection": actionable_detection,
        "actionable_false_positive": actionable_false_positive,
        "detection_delay_steps": detection_delay_steps,
        "samples": sample_index,
        "raw_goodput_at_risk": raw_state.goodput_at_risk,
        "actual_goodput_loss": round(actual_goodput_loss, 6),
        "goodput_calibration_error": round(
            abs(state.goodput_at_risk - actual_goodput_loss), 6
        ),
        "state": serialize_state(state),
        "selected_action": receipt.selected_action.value,
        "policy_reason": receipt.policy_reason,
        "state_digest": receipt.state_digest,
        "receipt_digest": receipt.receipt_digest,
        "ranked_actions": [
            serialize_action_score(score)
            for score in receipt.scores
        ],
    }


def benchmark(seeds: Iterable[int], fault: str) -> Dict[str, object]:
    runs = [run_scenario(seed, fault) for seed in seeds]
    raw_signaled = [run for run in runs if run["raw_signal_observed"]]
    background_signaled = [run for run in runs if run["background_raw_signals"] > 0]
    actionable = [run for run in runs if run["actionable_detection"]]
    false_actions = [run for run in runs if run["actionable_false_positive"]]
    interventions = [
        run for run in runs
        if run["selected_action"] not in {"observe", "throttle"}
    ]
    delays = [
        run["detection_delay_steps"]
        for run in runs
        if run["detection_delay_steps"] is not None
    ]
    return {
        "fault": fault,
        "runs": len(runs),
        "raw_signal_runs": len(raw_signaled),
        "raw_signal_rate": round(len(raw_signaled) / max(len(runs), 1), 6),
        "background_raw_signal_runs": len(background_signaled),
        "background_raw_signal_rate": round(
            len(background_signaled) / max(len(runs), 1), 6
        ),
        "actionable_detections": len(actionable),
        "actionable_detection_rate": round(
            len(actionable) / max(len(runs), 1), 6
        ),
        "actionable_false_positives": len(false_actions),
        "actionable_false_positive_rate": round(
            len(false_actions) / max(len(runs), 1), 6
        ),
        "mean_detection_delay_steps": (
            round(sum(delays) / len(delays), 6) if delays else None
        ),
        "top1_attribution_accuracy": round(
            sum(bool(run["top1_correct"]) for run in runs) / max(len(runs), 1),
            6,
        ),
        "disruptive_interventions": len(interventions),
        "mean_goodput_at_risk": round(
            sum(run["state"]["goodput_at_risk"] for run in runs) / max(len(runs), 1),
            6,
        ),
        "mean_actual_goodput_loss": round(
            sum(run["actual_goodput_loss"] for run in runs) / max(len(runs), 1),
            6,
        ),
        "mean_goodput_calibration_error": round(
            sum(run["goodput_calibration_error"] for run in runs) / max(len(runs), 1),
            6,
        ),
        "action_counts": {
            action: sum(run["selected_action"] == action for run in runs)
            for action in sorted({run["selected_action"] for run in runs})
        },
        "receipt_digests": [run["receipt_digest"] for run in runs],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--fault",
        choices=[
            "network_straggler",
            "gpu_thermal_drift",
            "storage_degradation",
            "healthy",
        ],
        default="network_straggler",
    )
    parser.add_argument("--benchmark", action="store_true")
    args = parser.parse_args()

    if args.benchmark:
        result = benchmark(range(args.seed, args.seed + 16), args.fault)
    else:
        result = run_scenario(args.seed, args.fault)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
