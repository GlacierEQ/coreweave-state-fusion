# AGENTS.md — coreweave-state-fusion

**Company:** CoreWeave
**Domain:** Datacenter Compute & GPU Cluster Orchestration

## Quick Rules
- **Test command:** `PYTHONPATH=src pytest tests/ -v`
- **Lint:** `ruff check src/ tests/`
- **No drive-by edits** — load the skill first.

## Architecture
- `src/coreweave_state_fusion/core.py` — Domain logic (Datacenter Compute & GPU Cluster Orchestration)
- `tests/` — Verified test suite
- `.github/workflows/ci.yml` — Enforced CI pipeline
