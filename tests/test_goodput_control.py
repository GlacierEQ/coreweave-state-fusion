import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from failure_lab import benchmark, run_scenario
from goodput_control import (
    Action,
    Component,
    CounterfactualPlanner,
    Layer,
    RecoveryPolicy,
    RemediationContext,
    StateFusionEngine,
    TelemetrySample,
    TopologyGraph,
    build_demo_topology,
)


class TopologyTests(unittest.TestCase):
    def test_blast_radius_propagates_to_job(self):
        topology = build_demo_topology()
        impacted = topology.blast_radius("gpu-0")
        self.assertIn("node-0", impacted)
        self.assertIn("job-0", impacted)

    def test_unknown_dependency_fails_closed(self):
        topology = TopologyGraph()
        topology.register(Component("job", Layer.JOB, dependencies=("missing",)))
        with self.assertRaises(ValueError):
            topology.validate()


class FusionTests(unittest.TestCase):
    def test_healthy_run_remains_low_risk(self):
        result = run_scenario(seed=11, fault="healthy")
        self.assertLess(result["state"]["system_risk"], 0.20)
        self.assertLess(result["state"]["goodput_at_risk"], 0.20)
        self.assertEqual(result["selected_action"], "observe")

    def test_network_straggler_generates_cross_layer_risk(self):
        result = run_scenario(seed=7, fault="network_straggler")
        state = result["state"]
        self.assertGreater(state["system_risk"], 0.20)
        self.assertGreater(state["goodput_at_risk"], 0.20)
        signal_components = {signal["component_id"] for signal in state["signals"]}
        self.assertIn("nic-0", signal_components)
        self.assertIn("job-0", signal_components)

    def test_state_digest_is_deterministic(self):
        first = run_scenario(seed=19, fault="storage_degradation")
        second = run_scenario(seed=19, fault="storage_degradation")
        self.assertEqual(first["state_digest"], second["state_digest"])
        self.assertEqual(first["receipt_digest"], second["receipt_digest"])


class PolicyTests(unittest.TestCase):
    def _degraded_state(self):
        topology = build_demo_topology()
        engine = StateFusionEngine(topology)
        for step in range(20):
            engine.ingest(TelemetrySample("gpu-0", "sm_util", 0.9, step))
            engine.ingest(TelemetrySample("job-0", "step_time_s", 1.0, step))
        for step in range(20, 28):
            engine.ingest(
                TelemetrySample("gpu-0", "sm_util", 0.4 - (step - 20) * 0.02, step)
            )
            engine.ingest(
                TelemetrySample("job-0", "step_time_s", 2.0 + (step - 20) * 0.2, step)
            )
        return engine.fuse()

    def test_low_confidence_blocks_disruptive_actions(self):
        state = self._degraded_state()
        planner = CounterfactualPlanner(RecoveryPolicy(minimum_confidence=0.65))
        context = RemediationContext(
            confidence=0.30,
            checkpoint_freshness=0.9,
            replacement_capacity=0.9,
            workload_priority=0.9,
            recurrence_risk=0.7,
        )
        receipt = planner.choose(state, context)
        disruptive = {
            Action.ISOLATE_GPU,
            Action.DRAIN_NODE,
            Action.CHECKPOINT_REQUEUE,
            Action.REROUTE,
        }
        for score in receipt.scores:
            if score.action in disruptive:
                self.assertFalse(score.allowed)
        self.assertIn(receipt.selected_action, {Action.OBSERVE, Action.THROTTLE})

    def test_reroute_fails_closed_without_capacity(self):
        state = self._degraded_state()
        planner = CounterfactualPlanner()
        context = RemediationContext(
            confidence=0.95,
            checkpoint_freshness=0.9,
            replacement_capacity=0.0,
            workload_priority=0.9,
            recurrence_risk=0.7,
        )
        receipt = planner.choose(state, context)
        reroute = next(score for score in receipt.scores if score.action == Action.REROUTE)
        self.assertFalse(reroute.allowed)
        self.assertIn("replacement capacity", reroute.reason)

    def test_receipt_is_json_serializable(self):
        result = run_scenario(seed=23, fault="gpu_thermal_drift")
        encoded = json.dumps(result, sort_keys=True)
        self.assertIn("receipt_digest", encoded)


class AttributionTests(unittest.TestCase):
    def test_network_fault_attributes_nic(self):
        result = run_scenario(seed=7, fault="network_straggler")
        self.assertEqual(result["top_cause"], "nic-0")
        self.assertTrue(result["top1_correct"])

    def test_gpu_fault_attributes_gpu(self):
        result = run_scenario(seed=7, fault="gpu_thermal_drift")
        self.assertEqual(result["top_cause"], "gpu-1")
        self.assertTrue(result["top1_correct"])

    def test_storage_fault_attributes_storage(self):
        result = run_scenario(seed=7, fault="storage_degradation")
        self.assertEqual(result["top_cause"], "storage-0")
        self.assertTrue(result["top1_correct"])

    def test_healthy_run_emits_no_root_cause(self):
        result = run_scenario(seed=11, fault="healthy")
        self.assertIsNone(result["top_cause"])
        self.assertTrue(result["top1_correct"])

    def test_fault_has_measured_synthetic_goodput_loss(self):
        fault = run_scenario(seed=7, fault="network_straggler")
        healthy = run_scenario(seed=7, fault="healthy")
        self.assertGreater(fault["actual_goodput_loss"], healthy["actual_goodput_loss"])


class BenchmarkTests(unittest.TestCase):
    def test_fault_benchmark_detects_majority(self):
        result = benchmark(range(1, 9), "network_straggler")
        self.assertGreaterEqual(result["detection_rate"], 0.75)

    def test_healthy_benchmark_avoids_disruptive_intervention(self):
        result = benchmark(range(1, 9), "healthy")
        self.assertEqual(result["disruptive_interventions"], 0)

    def test_attribution_accuracy_is_reported(self):
        result = benchmark(range(1, 9), "storage_degradation")
        self.assertGreaterEqual(result["top1_attribution_accuracy"], 0.75)

    def test_goodput_calibration_error_is_reported(self):
        result = benchmark(range(1, 9), "network_straggler")
        self.assertGreaterEqual(result["mean_goodput_calibration_error"], 0.0)
        self.assertLessEqual(result["mean_goodput_calibration_error"], 1.0)


if __name__ == "__main__":
    unittest.main()
