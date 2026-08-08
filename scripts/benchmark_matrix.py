#!/usr/bin/env python3
"""Generate a deterministic synthetic benchmark receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from failure_lab import benchmark  # noqa: E402
from goodput_control import canonical_json  # noqa: E402

FAULTS = (
    "healthy",
    "network_straggler",
    "gpu_thermal_drift",
    "storage_degradation",
)


def build_matrix(seed_start: int = 1, seed_count: int = 16) -> dict:
    if seed_count < 1:
        raise ValueError("seed_count must be positive")
    seeds = range(seed_start, seed_start + seed_count)
    scenarios = {fault: benchmark(seeds, fault) for fault in FAULTS}
    payload = {
        "schema": "glaciereq.goodput.synthetic-benchmark.v1",
        "scope": "deterministic_synthetic_failure_lab_only",
        "seed_start": seed_start,
        "seed_count": seed_count,
        "scenarios": scenarios,
        "claim_boundary": (
            "Synthetic lab evidence only. No production workload, employer deployment, "
            "or production performance claim is represented."
        ),
    }
    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return {**payload, "benchmark_digest": digest}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-count", type=int, default=16)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = build_matrix(args.seed_start, args.seed_count)
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
