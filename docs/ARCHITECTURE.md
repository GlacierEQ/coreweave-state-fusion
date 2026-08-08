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
| `coreweave-entropy-engine` | experimental donor | entropy hypothesis; requires benchmark validation |
| `coreweave-circuit-breaker` | policy donor | simple 3-strike circuit-breaker prototype |
| `coreweave-temporal-router` | placement donor | static weighted placement despite earlier time-expanded claim |
| `nvidia-gpu-health` | adjacent reference donor | GPU thermal/power/occupancy health demo with tests/integrity scaffolding |

No donor is represented as independently proven production infrastructure.

## Current control loop

```text
TopologyGraph
   |
TelemetrySample
   |
RollingBaselineDetector ----- EntropyMonitor (experimental)
   |                               |
   +------------ StateFusionEngine-+
                    |
              component/layer risk
                    |
              GoodputModel
                    |
            goodput_at_risk
                    |
          CounterfactualPlanner
                    |
             RecoveryPolicy
                    |
             RecoveryReceipt
```

## Safety invariants

1. Unknown topology dependencies fail validation.
2. Unknown telemetry components fail ingestion.
3. Isolated statistical excursions remain evidence but do not become actionable degradation.
4. Disruptive recovery requires persistent risk across at least two components.
5. Low fault confidence blocks disruptive action.
6. Reroute requires replacement capacity.
7. Checkpoint/requeue requires minimally fresh checkpoint state.
8. Identical state + context produces deterministic receipt digests.
9. Entropy remains experimental until it wins a controlled benchmark.
10. No performance claim is promoted from source comments alone.

## Next engineering delta

The next slice adds explicit causal attribution and benchmark baselines:

- static threshold detector;
- rolling-z detector;
- cross-layer fusion;
- fusion + attribution;
- full planner.

Metrics:

- fault detection precision/recall;
- false-positive rate;
- detection lead time;
- root-cause top-1/top-3 accuracy;
- goodput loss;
- unnecessary disruption;
- recovery regret;
- mean time to recovery.
