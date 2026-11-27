# CoreWeave State Fusion

A private GlacierEQ R&D prototype for **freshness-aware fusion of overlapping infrastructure telemetry**.

## Implemented mechanism

`StateFusionEngine` now:

- rejects invalid confidence values;
- excludes observations older than a configured freshness window;
- combines overlapping metrics with explicit confidence weighting;
- refuses to invent a fused value when all contributors have zero confidence;
- retains per-metric contributor provenance;
- computes confidence-weighted health only from fresh layers;
- reports stale layers and unresolved metrics explicitly.

## Truth boundary

This repository is not evidence of CoreWeave affiliation, production deployment, cluster reliability improvement, or inference-drift reduction. It is an independent prototype mechanism.

The earlier wording said it "solves" cluster reliability and inference drift. That exceeded the repository evidence. The current claim is narrower: the code implements a bounded state-fusion primitive whose usefulness still requires integration and runtime evaluation.

## Verification

```bash
python -m unittest discover -s tests -v
python src/state_fusion.py
```

CI is configured against the actual default branch, `master`.

## Promotion gates

Before this experiment can become a canonical system component, it still needs:

- a positive hosted test receipt;
- larger synthetic and replayed telemetry scenarios;
- explicit units/schema semantics for cross-source metrics;
- clock-skew and out-of-order observation tests;
- integration evidence showing where fused state changes an operational decision;
- measured comparison against a simpler last-value or per-layer baseline.
