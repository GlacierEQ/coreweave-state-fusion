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
  -> bounded behavioral evidence
  -> topology-aware state fusion
  -> actionable cross-layer degradation
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

### Auditable module boundaries

The original control-plane surface is preserved through `src/goodput_control.py`,
while implementation responsibilities are split into:

- `control_types.py` — types, topology, canonical serialization, digests;
- `detectors.py` — rolling baseline, trend, entropy, harmful-direction policy;
- `fusion_engine.py` — bounded evidence fusion and raw goodput risk;
- `recovery.py` — fail-closed policy and Recovery Regret planning;
- `attribution.py` — topology-aware probable root-cause ranking;
- `calibration.py` — explicitly synthetic-only goodput calibration.

### Signal is not actionability

`RollingBaselineDetector` can emit statistical signals during healthy synthetic
runs. The controller does **not** equate a raw z-score excursion with a failure.
Actionable degradation requires persistent harmful evidence across at least two
components plus system/goodput risk gates.

The failure lab separately records background raw signals, actionable false
positives, post-injection detection time, and final recovery action.

### Bounded and recoverable evidence

Historical anomalies no longer live forever. `StateFusionEngine` expires raw
signals using a bounded evidence TTL. Snapshot-only trend evidence is not
appended back into history, so repeated `fuse()` calls without new telemetry are
idempotent instead of manufacturing persistence.

### Direction-aware risk

Automatic degradation scoring is conservative about whether movement is
harmful. Higher latency/step time/error pressure is harmful; lower utilization,
throughput, bandwidth, goodput, or health is harmful. Beneficial movements stay
observable without being promoted into intervention risk. Unknown semantics do
not authorize automatic degradation scoring.

### Input and entropy hardening

Non-finite telemetry values/timestamps are rejected before state mutation.
Constant entropy windows return zero safely; invalid/zero-width binning cannot
enter the entropy calculation.

`EntropyMonitor` remains explicitly experimental. The code does **not** claim
that entropy predicts production failures.

### Root-cause attribution

`RootCauseAttributor` ranks probable initiating components from current local
risk, downstream pressure, and topology blast radius. It is an attribution
heuristic, not proof of physical causality.

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

### Machine-verifiable receipts

Each fused state and recovery decision receives a deterministic SHA-256 digest
over canonical JSON. `scripts/benchmark_matrix.py` generates a bounded synthetic
benchmark receipt that records aggregate evidence plus the number of per-run
receipts rather than embedding every run digest in the matrix.

## Deterministic synthetic benchmark

Generate the matrix:

```bash
python3 scripts/benchmark_matrix.py --output benchmarks/synthetic-v1.json
```

Current committed bounded receipt (`glaciereq.goodput.synthetic-benchmark.v2`):

`a9b754e61c95829e0fb10d33ef7d2b253d7bcbd0351e8ad582ca05bc6761f25c`

Across 16 seeded runs per scenario in the deterministic synthetic lab:

| Scenario | Actionable detection | Actionable false positives | Mean detection delay | Top-1 attribution | Disruptive actions | Mean calibrated goodput error |
|---|---:|---:|---:|---:|---:|---:|
| healthy | 0% | 0% | — | 100% no-cause classification | 0 / 16 | 0.001694 |
| network straggler | 100% | 0% | 1.75 steps | 100% | 16 / 16 | 0.024901 |
| GPU drift proxy | 100% | 0% | 2.8125 steps | 100% | 16 / 16 | 0.014609 |
| storage degradation | 100% | 0% | 1.875 steps | 100% | 16 / 16 | 0.060702 |

A deliberately important result: raw statistical signals occur in all healthy
synthetic runs, but **actionable detection remains 0%, actionable false-positive
rate remains 0%, and disruptive actions remain 0/16**. That separation prevents
ordinary statistical noise from becoming an intervention claim.

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

Current local contract suite: **25 tests**. In addition to the original topology,
policy, attribution, determinism, and benchmark contracts, review hardening now
covers:

- constant-value entropy safety;
- non-finite telemetry rejection before mutation;
- snapshot idempotence;
- stale evidence expiry after recovery;
- beneficial-direction exclusion from degradation risk;
- post-injection actionable-detection timing;
- healthy actionable false-positive protection.

GitHub-hosted Actions verification is currently unable to start because the
repository account's Actions budget blocks runner use. The workflow remains in
place and will compile, run the contracts, verify deterministic scenario output,
and regenerate/byte-compare the benchmark receipt when hosted execution is
available.

## Promotion roadmap

| Gate | State | Required evidence |
|---|---|---|
| P0 Truth | built | donor lineage reconciled; unsupported performance/novelty claims removed |
| P1 Failure Lab | built / synthetic | deterministic seeded fault injection and replay |
| P2 State Graph | built | workload -> node -> GPU/NIC/storage dependency traversal |
| P3 Detection | built / synthetic | raw/actionable boundary and post-injection timing; comparative baselines still required |
| P4 Attribution | built / synthetic | probable root-cause ranking against injected faults |
| P5 Goodput Risk | partial | synthetic calibration built; real trace calibration required |
| P6 Planner | built / synthetic | Recovery Regret planner; comparative intervention baseline still required |
| P7 Control Plane | partial | fail-closed policy + evidence expiry built; real idempotent action adapters/rollback required |
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
