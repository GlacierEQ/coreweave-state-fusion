# Architecture and lineage

## Canonical identity

**Goodput Autonomic Control Plane** is the successor system identity.

The GitHub repository retains the historical `coreweave-state-fusion` name for
lineage continuity. Employer-specific naming is not part of the canonical
system identity.

## Donor lineage

| Donor | Status in successor | Current truth |
|---|---|---|
| `coreweave-state-fusion` | canonical host / predecessor | weighted metric fusion prototype |
| `coreweave-shadow-monitor` | detector donor | rolling baseline, z-score, trend prototype |
| `coreweave-entropy-engine` | experimental donor | entropy hypothesis; not promoted as failure prediction |
| `coreweave-circuit-breaker` | policy donor | simple 3-strike circuit-breaker prototype |
| `coreweave-temporal-router` | placement donor | static weighted placement despite earlier time-expanded claim |
| `nvidia-gpu-health` | adjacent reference donor | GPU thermal/power/occupancy health demo with tests/integrity scaffolding |

No donor is represented as independently proven production infrastructure.

## Module boundaries

```text
control_types.py
  types + topology + canonical serialization + digests
        |
detectors.py ------------------------------+
  rolling-z / trend / entropy              |
  harmful-direction semantics              |
        |                                   |
fusion_engine.py                            |
  evidence TTL + idempotent snapshots      |
  component/layer risk + raw goodput risk  |
        |                                   |
attribution.py                              |
  probable root-cause ranking               |
        |                                   |
calibration.py                              |
  synthetic-only calibration                |
        |                                   |
recovery.py                                 |
  Recovery Regret + fail-closed policy      |
        |                                   |
goodput_control.py                          |
  stable compatibility/export surface <----+
```

## Control loop

```text
TelemetrySample
   |
finite/order validation
   |
RollingBaselineDetector ----- EntropyMonitor (experimental)
   |                               |
bounded timestamped evidence      |
   +------------ StateFusionEngine-+
                    |
        harmful-direction filtering
                    |
         component / layer risk
                    |
           raw GoodputModel
                    |
       explicit lab calibration
                    |
         RootCauseAttributor
                    |
          CounterfactualPlanner
                    |
             RecoveryPolicy
                    |
             RecoveryReceipt
```

## Truth layers

The implementation keeps four concepts separate:

1. **Raw statistical signal** — a detector saw a sufficiently unusual sample.
2. **Current harmful evidence** — the movement is semantically adverse and has
   not expired from the bounded evidence window.
3. **Actionable degradation** — persistent cross-layer evidence crosses the
   controller's system/goodput gates.
4. **Recovery authorization** — a candidate action additionally satisfies
   confidence, checkpoint, and capacity policy.

A raw signal is not a failure declaration and is never by itself authorization
to disrupt a workload.

## Evidence lifetime and snapshot semantics

The engine retains raw anomaly evidence only for a bounded TTL. Old anomalies
therefore cannot keep a recovered component permanently degraded.

Trend evidence is computed for a snapshot and is not appended into the raw
history. Entropy history is updated at most once for a telemetry timestamp.
Consequently, repeated `fuse()` calls without new telemetry are idempotent and
cannot manufacture additional persistence merely because state was read again.

## Metric direction semantics

Automatic risk promotion is conservative:

- rising latency, step time, temperature, error/ECC/retry/retransmit, packet
  loss, or queue pressure is harmful;
- falling utilization, throughput, bandwidth, goodput, or health is harmful;
- the opposite movement is not promoted as degradation;
- unknown metric semantics remain observable but do not authorize automatic
  degradation scoring.

This prevents improving workload behavior from being interpreted as a reason to
reroute or drain infrastructure.

## Input and entropy safety

Telemetry values and timestamps must be finite, and timestamps must be
non-decreasing. Validation occurs before detector or state mutation.

Entropy calculation fails safely on constant windows and invalid zero-width
ranges. Entropy remains an experimental feature whose incremental value must be
shown by comparative benchmark evidence before promotion.

## Attribution

`RootCauseAttributor` ranks probable initiating components using current local
risk, downstream risk pressure, topology blast radius, and a small
infrastructure source prior. It is an attribution heuristic, not proof of
physical causality.

The deterministic synthetic corpus injects three known roots:

- network straggler -> `nic-0`
- GPU drift -> `gpu-1`
- storage degradation -> `storage-0`

Those cases test regression behavior; they do not establish real-fleet
diagnostic accuracy.

## Goodput calibration boundary

`GoodputModel` remains a raw structural risk heuristic. Synthetic calibration is
applied only inside the failure lab by `SyntheticGoodputCalibrator`.

This prevents a coefficient fitted to synthetic workload timing from silently
becoming a production model constant. Real trace replay must replace or
recalibrate it before any external performance claim is eligible.

## Safety invariants

1. Unknown topology dependencies fail validation.
2. Unknown telemetry components fail ingestion.
3. Non-finite telemetry is rejected before state mutation.
4. Out-of-order telemetry timestamps fail closed.
5. Constant entropy windows return zero without unsafe binning.
6. Raw statistical excursions do not equal actionable degradation.
7. Only harmful-direction evidence contributes to automatic degradation risk.
8. Historical anomaly evidence expires after its bounded TTL.
9. Repeated snapshots without new telemetry are idempotent.
10. Disruptive recovery requires persistent risk across at least two components.
11. Low fault confidence blocks disruptive action.
12. Reroute requires replacement capacity.
13. Checkpoint/requeue requires minimally fresh checkpoint state.
14. Identical seeded scenarios produce deterministic state and recovery receipts.
15. The benchmark matrix is regenerated and byte-compared to its committed receipt.
16. Synthetic evidence is never represented as employer or production evidence.

## Current synthetic evidence gate

`benchmarks/synthetic-v1.json` is generated by `scripts/benchmark_matrix.py` over
16 deterministic seeds for each of four scenarios. The bounded matrix uses
schema `glaciereq.goodput.synthetic-benchmark.v2` and records aggregate evidence
plus per-scenario run-receipt cardinality without embedding all 64 run digests.

Current benchmark digest:

`a9b754e61c95829e0fb10d33ef7d2b253d7bcbd0351e8ad582ca05bc6761f25c`

The matrix explicitly separates background raw signals from post-injection
actionable detection. Current synthetic regression results include:

- healthy: 0% actionable detection, 0% actionable false positives, 0/16
  disruptive interventions;
- network straggler: 100% actionable detection, 0% actionable false positives,
  1.75-step mean post-injection detection delay;
- GPU drift proxy: 100% actionable detection, 0% actionable false positives,
  2.8125-step mean delay;
- storage degradation: 100% actionable detection, 0% actionable false
  positives, 1.875-step mean delay;
- current injected fault families: 100% top-1 attribution in this deterministic
  corpus only.

These are synthetic regression properties, not production performance claims.

## Verification state

The current local contract suite contains **25 tests**, including dedicated
regressions for constant entropy, non-finite input, snapshot idempotence,
evidence expiry, beneficial metric movement, and post-injection detection
semantics.

The hosted GitHub Actions workflow is configured to compile source/tests/scripts,
run contracts, verify repeated seeded output, and regenerate/byte-compare the
benchmark receipt. GitHub currently prevents the runner from starting because
an Actions budget limit is active; that infrastructure block must not be
reported as a code-test failure or a hosted pass.

## Next engineering delta

The highest-value next slice is **comparative baselining + intervention
verification**, not another detector:

- static threshold baseline;
- rolling-z-only baseline;
- fusion without attribution/planning;
- fusion + attribution;
- full Recovery Regret planner;
- simulated post-action state transition;
- explicit verified-recovery, rollback, and escalation states.

Primary measurements:

- actionable precision / recall;
- healthy false-action rate;
- post-injection detection lead time;
- root-cause top-1/top-3 accuracy;
- goodput calibration error;
- unnecessary disruption;
- recovery regret;
- time to verified recovery.
