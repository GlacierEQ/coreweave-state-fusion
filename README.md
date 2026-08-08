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
  -> goodput-at-risk estimate
  -> counterfactual action scores
  -> fail-closed safety policy
  -> selected recovery action
  -> deterministic recovery receipt
```

## Innovation thesis: Recovery Regret

The current implementation scores each candidate action against five explicit
cost terms:

1. expected lost useful compute after the action;
2. intervention disruption;
3. false-positive cost;
4. recovery latency;
5. recurrence risk.

The lowest-regret action is eligible only if the safety policy allows it.
Disruptive actions fail closed when confidence, checkpoint state, or replacement
capacity is insufficient.

This is a research/engineering hypothesis until measured against stronger
baselines. No production impact, CoreWeave deployment, or performance uplift is
claimed.

## What exists now

### Topology state graph

`TopologyGraph` models workload-to-infrastructure dependencies and computes
blast radius through those dependencies.

### Persistent degradation evidence

`RollingBaselineDetector` scores a sample against its prior behavioral window.
`StateFusionEngine` intentionally refuses to promote isolated statistical
excursions into component degradation. Automatic action requires persistent
risk on at least two components.

### Experimental entropy signal

`EntropyMonitor` computes normalized Shannon entropy over recent quantized
metric distributions and tracks entropy acceleration. This is explicitly an
experimental signal to benchmark; the code does **not** claim that entropy
predicts failure.

### Goodput-at-risk

`GoodputModel` maps component risk and topology blast radius into an estimated
fraction of useful work at risk. It is currently a transparent heuristic and is
designed to be replaced/calibrated with workload evidence.

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
over canonical JSON. Repeating the same seeded scenario produces the same state
and receipt digests.

## Failure lab

The deterministic failure lab currently supports:

- healthy baseline;
- network straggler;
- GPU utilization/thermal-drift proxy;
- storage degradation.

Run one scenario:

```bash
python3 src/failure_lab.py --seed 7 --fault network_straggler
```

Run a 16-seed benchmark:

```bash
python3 src/failure_lab.py --seed 1 --fault network_straggler --benchmark
```

The current failure lab is synthetic. It exists to make policy and detector
behavior reproducible before real trace replay is introduced.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The first successor slice covers:

- topology blast-radius propagation;
- unknown dependency fail-closed behavior;
- healthy-run low-risk/no-op behavior;
- cross-layer network-straggler evidence;
- deterministic state and recovery receipt hashes;
- low-confidence disruptive-action blocking;
- reroute capacity gating;
- JSON-serializable receipts;
- fault benchmark detection;
- healthy benchmark protection against disruptive intervention.

## Promotion roadmap

| Gate | Required evidence |
|---|---|
| P0 Truth | Reconcile donor lineage and remove unsupported novelty/performance claims |
| P1 Failure Lab | Deterministic seeded fault injection and replay |
| P2 State Graph | Workload -> node -> GPU/NIC/storage dependency traversal |
| P3 Detection | Precision/recall, false-positive rate, detection lead time |
| P4 Attribution | Probable root-cause ranking against known injected faults |
| P5 Goodput Risk | Calibrated predicted useful-compute loss |
| P6 Planner | Counterfactual remediation measured against fixed baselines |
| P7 Control Plane | Idempotent actions, rollback, safety boundaries |
| P8 Temporal Placement | Real future-window/topology-aware scheduling |
| P9 Verification | Post-action proof that state improved or rollback/escalation fired |
| P10 Evidence | Reproducible benchmark corpus + immutable receipts |
| P11 Projection | Recruiter/Master/Machine/Mesh render from measured proof |

## Truth boundary

This repository is independent GlacierEQ engineering. It does not claim
CoreWeave, NVIDIA, OpenAI, or any other company affiliation, proprietary access,
production deployment, or measured production benefit.

Company-specific application claims must be projections of verified evidence
from this system, never the source of the engineering claim itself.
