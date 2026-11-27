from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from state_fusion import InfrastructureLayer, StateFusionEngine  # noqa: E402

NOW = 1_000_000.0


class StateFusionTests(unittest.TestCase):
    def test_overlapping_metric_uses_confidence_weighting(self) -> None:
        engine = StateFusionEngine(max_age_s=60.0)
        engine.update_layer(
            InfrastructureLayer("a", {"util": 0.5}, 1.0, NOW, "HEALTHY")
        )
        engine.update_layer(
            InfrastructureLayer("b", {"util": 1.0}, 0.5, NOW, "DEGRADED")
        )

        result = engine.fuse(now=NOW)

        self.assertEqual(result["fused_metrics"]["util"], 0.6667)
        self.assertEqual(result["layers_fused"], 2)
        self.assertEqual(len(result["metric_provenance"]["util"]), 2)

    def test_stale_layer_is_excluded(self) -> None:
        engine = StateFusionEngine(max_age_s=10.0)
        engine.update_layer(
            InfrastructureLayer("fresh", {"latency": 2.0}, 1.0, NOW, "HEALTHY")
        )
        engine.update_layer(
            InfrastructureLayer(
                "stale",
                {"latency": 100.0},
                1.0,
                NOW - 11,
                "CRITICAL",
            )
        )

        result = engine.fuse(now=NOW)

        self.assertEqual(result["fused_metrics"]["latency"], 2.0)
        self.assertEqual(result["stale_layers"], ["stale"])
        self.assertEqual(result["layers_fused"], 1)

    def test_zero_confidence_metric_fails_closed(self) -> None:
        engine = StateFusionEngine()
        engine.update_layer(
            InfrastructureLayer("a", {"temperature": 70.0}, 0.0, NOW)
        )
        engine.update_layer(
            InfrastructureLayer("b", {"temperature": 80.0}, 0.0, NOW)
        )

        result = engine.fuse(now=NOW)

        self.assertNotIn("temperature", result["fused_metrics"])
        self.assertEqual(result["unresolved_metrics"], ["temperature"])
        self.assertIsNone(result["overall_health"])

    def test_invalid_confidence_is_rejected(self) -> None:
        engine = StateFusionEngine()

        with self.assertRaises(ValueError):
            engine.update_layer(
                InfrastructureLayer("bad", {"metric": 1.0}, 1.1, NOW)
            )

    def test_all_stale_returns_explicit_empty_state(self) -> None:
        engine = StateFusionEngine(max_age_s=5.0)
        engine.update_layer(
            InfrastructureLayer("old", {"metric": 1.0}, 1.0, NOW - 10)
        )

        result = engine.fuse(now=NOW)

        self.assertEqual(result["layers_fused"], 0)
        self.assertEqual(result["stale_layers"], ["old"])
        self.assertEqual(result["fused_metrics"], {})


if __name__ == "__main__":
    unittest.main()
