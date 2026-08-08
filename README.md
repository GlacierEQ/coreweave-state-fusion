# Goodput Autonomic Control Plane

> Canonical successor build hosted in the historical `coreweave-state-fusion`
> repository. The system identity is company-neutral; CoreWeave is the first
> employer projection, not the product boundary.

This branch consolidates five earlier CoreWeave-directed experiments into one
testable control loop:

- `coreweave-state-fusion` — cross-layer state synthesis
- `coreweave-shadow-monitor` — baseline / drift detection
- `coreweave-entropy-engine` — experimental disorder signal
- `coreweave-circuit-breaker` — bounded isolation and recovery
- `coreweave-temporal-router` — recovery-aware placement direction

`GlacierEQ/nvidia-gpu-health` is an adjacent GPU-health donor/reference. It is
not silently merged into this lineage.

## Problem

Long-running accelerator workloads can remain alive while useful throughput
degrades because a GPU, network path, storage dependency, or scheduler path is
slow rather than completely dead. Threshold-only monitoring can detect symptoms
without answering the higher-value question:

**Which safe intervention preserves the most useful compute?**

```text
telemetry
  -> topology-aware state fusion
  -> persistent degradation evidence
  -> probable root-cause ranking
  -> calibrated lab goodput-at-risk
  -> counterfactual action scores
  -> fail-closed safety policy
  -> selected recovery action
  -> deterministic recovery receipt
```

## Innovation thesis: Recovery Regret

The planner scores each candidate action against five explicit cost terms:

1. expected lost useful compute after the action;
2. intervention disruption;
3. false-positive cost;
4. recovery latency;
5. recurrence risk.

The lowest-regret action is eligible only if the safety policy allows it.
Disruptive actions fail closed when evidence confidence, checkpoint state, or
replacement capacity is insufficient.

This remains a research/engineering hypothesis until tested against stronger
baselines and real workload traces. No production impact, employer deployment,
or production performance uplift is claimed.

## Built now

### Topology state graph

`TopologyGraph` models workload-to-infrastructure dependencies and computes
blast radius through those dependencies.

### Raw signal vs actionable degradation

`RollingBaselineDetector` can emit statistical signals during both healthy and
faulted synthetic runs. `StateFusionEngine` therefore does **not** equate a raw
z-score excursion with a failure. Actionable degradation requires persistent
risk across at least two components plus system/goodput risk gates.

### Experimental entropy signal

`EntropyMonitor` computes normalized Shannon entropy over recent quantized
metric distributions and tracks entropy acceleration. It is explicitly an
experimental signal; the code does **not** claim that entropy predicts failure.

### Root-cause attribution

`RootCauseAttributor` ranks probable initiating components using persistent local
risk, topology blast radius, and downstream evidence. It is an attribution
heuristic, not proof of causality.

### Goodput-at-risk

The core `GoodputModel` remains a transparent structural heuristic. The
synthetic failure lab applies a separate `SyntheticGoodputCalibrator`; that
coefficient is scoped only to the deterministic synthetic corpus and is not a
production constant.

### Counterfactual remediation

`CounterfactualPlanner` compares:

- observe
- throttle
- isolate GPU
- drain node
- checkpoint + requeue
- reroute

using the Recovery Regret cost model.

### Fail-closed governance

`RecoveryPolicy` blocks disruptive actions when evidence is too weak or required
recovery capacity is unavailable.

### Machine-verifiable receipts

Each fused state and recovery decision receives a deterministic SHA-256 digest
over canonical JSON. `scripts/benchmark_matrix.py` also generates a deterministic
benchmark receipt and digest.

## Deterministic synthetic benchmark

Generate the full matrix:

```bash
python3 scripts/benchmark_matrix.py --output benchmarks/synthetic-v1.json
```

Current committed receipt:

`596615cc6ffb3324b826b683ad602ab49fd848ddc5a0dd7860cfa53f4f7caf45`

Across 16 seeded runs per scenario in the synthetic lab:

| Scenario | Actionable detection | Top-1 attribution | Disruptive actions | Mean calibrated goodput error |
|---|---:|---:|---:|---:|
| healthy | 0% | 100% no-cause classification | 0 / 16 | 0.044407 |
| network straggler | 100% | 100% | 16 / 16 | 0.024873 |
| GPU drift proxy | 100% | 100% | 16 / 16 | 0.015584 |
| storage degradation | 100% | 100% | 16 / 16 | 0.063914 |

A deliberately important result: **raw statistical signal rate is 100% even in
the healthy synthetic runs**, while actionable detection remains 0% and no
disruptive action occurs. This is why the control plane keeps signal,
degradation, and authorization as separate states.

These numbers are synthetic regression evidence only. They are not estimates of
real CoreWeave, OpenAI, NVIDIA, or other production-fleet performance.

## Failure lab

Run one scenario:

```bash
python3 src/failure_lab.py --seed 7 --fault network_straggler
```

Run a 16-seed scenario benchmark:

```bash
python3 src/failure_lab.py --seed 1 --fault network_straggler --benchmark
```

The current lab supports healthy baseline, network straggler, GPU drift proxy,
and storage degradation. Real trace replay is the next evidence class.

## Tests

```bash
python3 -m compileall -q src tests scripts
python3 -m unittest discover -s tests -v
```

Current local contract suite: **18 tests** covering topology validation,
blast-radius propagation, healthy no-op behavior, persistent cross-layer risk,
deterministic receipts, policy gating, attribution, synthetic goodput loss,
actionable detection, and raw-signal/actionability separation.

GitHub-hosted Actions verification is currently unable to start because the
repository account's Actions budget blocks runner use. The workflow remains in
place and also regenerates/byte-compares the benchmark receipt when hosted
execution becomes available.

## Promotion roadmap

| Gate | State | Required evidence |
|---|---|---|
| P0 Truth | built | donor lineage reconciled; unsupported performance/novelty claims removed |
| P1 Failure Lab | built / synthetic | deterministic seeded fault injection and replay |
| P2 State Graph | built | workload -> node -> GPU/NIC/storage dependency traversal |
| P3 Detection | partial | raw signal/actionable split built; comparative precision/recall still required |
| P4 Attribution | built / synthetic | probable root-cause ranking against injected faults |
| P5 Goodput Risk | partial | synthetic calibration built; real trace calibration required |
| P6 Planner | built / synthetic | Recovery Regret planner; baseline comparison still required |
| P7 Control Plane | partial | fail-closed policy built; real idempotent action adapters/rollback required |
| P8 Temporal Placement | not promoted | real future-window/topology-aware scheduling required |
| P9 Verification | next | prove post-action improvement or rollback/escalation |
| P10 Evidence | partial | deterministic synthetic benchmark + receipts built; real trace corpus required |
| P11 Projection | blocked by evidence | recruiter projection only after promotion gates support claims |

## Truth boundary

This repository is independent GlacierEQ engineering. It does not claim
CoreWeave, NVIDIA, OpenAI, or any other company affiliation, proprietary access,
production deployment, or measured production benefit.

Company-specific application claims must be projections of verified evidence
from this system, never the source of the engineering claim itself.
