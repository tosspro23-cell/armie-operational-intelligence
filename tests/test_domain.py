from __future__ import annotations

import json
import unittest
from pathlib import Path

from target_service.app.domain import RuntimeConfig, SyntheticPaymentService


ROOT = Path(__file__).resolve().parents[1]


class TargetServiceTests(unittest.TestCase):
    def _config(self, name: str) -> RuntimeConfig:
        raw = json.loads((ROOT / "fixtures" / name).read_text())
        return RuntimeConfig.from_mapping(raw)

    def test_normal_behavior_succeeds(self) -> None:
        result = SyntheticPaymentService(self._config("runtime_config_safe.json")).checkout(
            "order-1", 1099
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.outcome, "authorized")

    def test_fault_behavior_is_timeout(self) -> None:
        result = SyntheticPaymentService(self._config("runtime_config_fault.json")).checkout(
            "order-1", 1099
        )
        self.assertEqual(result.status_code, 504)
        self.assertEqual(result.error_code, "checkout_dependency_timeout")

    def test_fault_is_reproducible(self) -> None:
        service = SyntheticPaymentService(self._config("runtime_config_fault.json"))
        results = [service.checkout(f"order-{i}", 1099) for i in range(5)]
        self.assertEqual({result.status_code for result in results}, {504})
        self.assertEqual(service.checkout_timeouts, 5)

    def test_health_is_liveness_but_exposes_degraded_checkout(self) -> None:
        payload = SyntheticPaymentService(self._config("runtime_config_fault.json")).health()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["checkout_path"], "degraded")

    def test_contradictory_timeline_has_preincident_success_and_incident_timeout(self) -> None:
        timeline = json.loads((ROOT / "fixtures" / "incident_timeline.json").read_text())
        self.assertEqual(timeline["pre_incident_observation"]["downstream_latency_ms"], 118)
        self.assertEqual(timeline["pre_incident_observation"]["checkout_status"], 200)
        self.assertEqual(timeline["incident_observation"]["downstream_latency_ms"], 168)
        self.assertEqual(timeline["incident_observation"]["checkout_status"], 504)
        self.assertLess(
            timeline["timeout_budget_first_observed_at"], timeline["deployment_loaded_at"]
        )
