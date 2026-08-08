"""Deterministic failure lab for the Goodput Autonomic Control Plane."""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Dict, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


def run_scenario(seed: int, fault: str) -> Dict[str, object]:
    topology = build_demo_topology()
    engine = StateFusionEngine(topology)
    first_detection = None
    sample_count = 0

    for sample in generate_samples(seed=seed, fault=fault):
        signal = engine.ingest(sample)
        if signal and first_detection is None:
            first_detection = sample.timestamp
        sample_count += 1

    state = engine.fuse()
    planner = CounterfactualPlanner()
    context = RemediationContext(
        confidence=min(1.0, 0.55 + state.system_risk),
        checkpoint_freshness=0.85,
        replacement_capacity=0.70,
        workload_priority=0.90,
        recurrence_risk=0.65,
    )
    receipt = planner.choose(state, context)
    return {
        "seed": seed,
        "fault": fault,
        "first_detection_timestamp": first_detection,
        "samples": sample_count,
        "state": serialize_state(state),
        "selected_action": receipt.selected_action.value,
        "policy_reason": receipt.policy_reason,
        "state_digest": receipt.state_digest,
        "receipt_digest": receipt.receipt_digest,
        "ranked_actions": [serialize_action_score(score) for score in receipt.scores],
    }


def benchmark(seeds: Iterable[int], fault: str) -> Dict[str, object]:
    runs = [run_scenario(seed, fault) for seed in seeds]
    detected = [run for run in runs if run["first_detection_timestamp"] is not None]
    interventions = [
        run
        for run in runs
        if run["selected_action"] not in {"observe", "throttle"}
    ]
    return {
        "fault": fault,
        "runs": len(runs),
        "detections": len(detected),
        "detection_rate": round(len(detected) / max(len(runs), 1), 6),
        "disruptive_interventions": len(interventions),
        "mean_goodput_at_risk": round(
            sum(run["state"]["goodput_at_risk"] for run in runs) / max(len(runs), 1),
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
    result = (
        benchmark(range(args.seed, args.seed + 16), args.fault)
        if args.benchmark
        else run_scenario(args.seed, args.fault)
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
