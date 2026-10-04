from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException

from controller.events import EventCapture
from controller.web_api import ApprovalRequest, LocalConsole, live_run_snapshot, start_live_run


class WebConsoleContractTests(unittest.TestCase):
    @patch("controller.web_api.request_json")
    @patch("controller.web_api.wait_for_health", return_value={"status": 200, "body": {"status": "ok"}})
    @patch("controller.web_api.compose_up")
    @patch("controller.web_api.prepare_runtime")
    def test_reset_fault_leaves_target_ready_for_agents_api_start(
        self,
        prepare_runtime,
        compose_up,
        wait_for_health,
        request_json,
    ) -> None:
        request_json.side_effect = [
            {"status": 200, "body": {"checkout_timeouts": 0}},
            {"status": 200, "body": {"status": "ok", "observed_latency_ms": 168}},
            {"status": 200, "body": {"timeout_budget_ms": 120}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "reset-run"
            run_dir.mkdir(parents=True)
            capture = EventCapture(run_dir)
            console = LocalConsole()
            with patch("controller.web_api.new_run", return_value=(run_dir, capture)):
                console.reset_local()
                self.assertIsNotNone(console.worker)
                console.worker.join(timeout=1)  # type: ignore[union-attr]

        snapshot = console.snapshot()
        self.assertEqual(snapshot["phase"], "fault_ready")
        self.assertEqual(snapshot["target"]["health"]["status"], 200)
        self.assertIsNone(snapshot["target"]["last_checkout"])
        prepare_runtime.assert_called_once()
        compose_up.assert_called_once_with(force_recreate=True, reset_runtime_config=True)
        wait_for_health.assert_called_once()

    @patch("controller.web_api.write_probe_artifact")
    @patch("controller.web_api.snapshot_runtime")
    @patch("controller.web_api.validate_executor_boundary")
    @patch("controller.web_api.probe_incident", return_value=[
        {
            "label": "checkout_1",
            "status": 504,
            "body": {"error_code": "checkout_dependency_timeout"},
        }
    ])
    @patch("controller.web_api.request_json")
    @patch("controller.web_api.wait_for_health", return_value={"status": 200, "body": {"status": "ok"}})
    @patch("controller.web_api.compose_up")
    @patch("controller.web_api.prepare_runtime")
    def test_local_validation_is_evidence_only_and_does_not_request_approval(
        self,
        prepare_runtime,
        compose_up,
        wait_for_health,
        request_json,
        probe_incident,
        validate_executor_boundary,
        snapshot_runtime,
        write_probe_artifact,
    ) -> None:
        request_json.side_effect = [
            {"status": 200, "body": {"incident_window": "synthetic"}},
            {"status": 200, "body": {"checkout_timeouts": 1}},
            {"status": 200, "body": {"timeout_budget_ms": 120}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "local-run"
            run_dir.mkdir(parents=True)
            capture = EventCapture(run_dir)
            console = LocalConsole()
            with patch("controller.web_api.new_run", return_value=(run_dir, capture)):
                console.start_local()
                self.assertIsNotNone(console.worker)
                console.worker.join(timeout=1)  # type: ignore[union-attr]

        snapshot = console.snapshot()
        self.assertEqual(snapshot["phase"], "fault_ready")
        self.assertIsNone(snapshot["proposal"])
        self.assertIsNone(snapshot["approval"])
        self.assertEqual(snapshot["target"]["last_checkout"]["status"], 504)
        self.assertNotIn("approval.required", [event["type"] for event in console.event_snapshot()])
        self.assertIn("local.validation.completed", [event["type"] for event in console.event_snapshot()])
        prepare_runtime.assert_not_called()
        compose_up.assert_called_once_with(force_recreate=False, reset_runtime_config=False)
        wait_for_health.assert_called_once()
        validate_executor_boundary.assert_called_once_with(capture)
        probe_incident.assert_called_once_with(capture)
        snapshot_runtime.assert_called_once_with(run_dir)
        write_probe_artifact.assert_called_once_with(run_dir, probe_incident.return_value)

    @patch("controller.web_api.write_probe_artifact")
    @patch("controller.web_api.snapshot_runtime")
    @patch("controller.web_api.validate_executor_boundary")
    @patch("controller.web_api.probe_incident", return_value=[
        {
            "label": "checkout_1",
            "status": 200,
            "body": {"outcome": "authorized"},
        }
    ])
    @patch("controller.web_api.request_json")
    @patch("controller.web_api.wait_for_health", return_value={"status": 200, "body": {"status": "ok"}})
    @patch("controller.web_api.compose_up")
    @patch("controller.web_api.prepare_runtime")
    def test_local_validation_preserves_healthy_target_without_reintroducing_fault(
        self,
        prepare_runtime,
        compose_up,
        wait_for_health,
        request_json,
        probe_incident,
        validate_executor_boundary,
        snapshot_runtime,
        write_probe_artifact,
    ) -> None:
        request_json.side_effect = [
            {"status": 200, "body": {"incident_window": "synthetic"}},
            {"status": 200, "body": {"checkout_successes": 1, "checkout_timeouts": 0}},
            {"status": 200, "body": {"timeout_budget_ms": 300}},
        ]
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "healthy-run"
            run_dir.mkdir(parents=True)
            capture = EventCapture(run_dir)
            console = LocalConsole()
            with patch("controller.web_api.new_run", return_value=(run_dir, capture)):
                console.start_local()
                self.assertIsNotNone(console.worker)
                console.worker.join(timeout=1)  # type: ignore[union-attr]

        snapshot = console.snapshot()
        self.assertEqual(snapshot["phase"], "target_healthy")
        self.assertEqual(snapshot["target"]["last_checkout"]["status"], 200)
        self.assertIsNone(snapshot["proposal"])
        self.assertIsNone(snapshot["approval"])
        event_types = [event["type"] for event in console.event_snapshot()]
        self.assertNotIn("incident.reproduced", event_types)
        self.assertNotIn("approval.required", event_types)
        self.assertIn("local.validation.completed", event_types)
        prepare_runtime.assert_not_called()
        compose_up.assert_called_once_with(force_recreate=False, reset_runtime_config=False)

    def test_browser_live_start_requires_credentials_and_launches_one_run(self) -> None:
        import os
        from unittest.mock import Mock

        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "artifacts" / "runs" / "browser-run"
            with patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "controller-key",
                    "OPENAI_EXECUTOR_API_KEY": "executor-key",
                    "ARMIE_SRE_AGENT_ID": "saved-agent",
                    "OPENAI_PROJECT_ID": "project",
                },
                clear=False,
            ), patch(
                "controller.web_api.new_run",
                return_value=(run_dir, Mock()),
            ), patch(
                "controller.web_api.run_real",
                return_value=0,
            ) as run_real:
                result = start_live_run()
                self.assertEqual(result["status"], "accepted")
                self.assertEqual(result["run_id"], "browser-run")

                from controller.web_api import live_run_thread

                self.assertIsNotNone(live_run_thread)
                live_run_thread.join(timeout=1)  # type: ignore[union-attr]
                run_real.assert_called_once()
                self.assertEqual(run_real.call_args.kwargs["prepared_run"], run_dir)
                self.assertIsNotNone(run_real.call_args.kwargs["approval_provider"])

    def test_live_run_snapshot_is_read_only_and_redacted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "artifacts" / "runs" / "20261002T000000Z"
            run_dir.mkdir(parents=True)
            (run_dir / "session.json").write_text("{}", encoding="utf-8")
            (run_dir / "runtime_identity.json").write_text(
                json.dumps(
                    {
                        "agents_api_session_id": "sess_test",
                        "agents_api_environment_id": "env_test",
                        "configured_model": "gpt-6-luna",
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "controller_events.jsonl").write_text(
                "\n".join(
                    json.dumps({"kind": kind, "captured_at": "2026-10-02T00:00:00Z"})
                    for kind in ("session_created", "environment_connected")
                ),
                encoding="utf-8",
            )
            (run_dir / "agents_api_events.jsonl").write_text(
                json.dumps(
                    {
                        "payload": {
                            "event": {"type": "agent.session.turn.completed"}
                        }
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "target_probe.jsonl").write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "label": "health",
                                "status": 200,
                                "body": {"version": "target-v1", "checkout_path": "degraded"},
                            }
                        ),
                        json.dumps({"label": "checkout_1", "status": 504}),
                        json.dumps(
                            {
                                "label": "health",
                                "status": 200,
                                "body": {"version": "target-v2", "checkout_path": "ready"},
                            }
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            (run_dir / "remediation_proposal_final.md").write_text(
                "No API key here.\n", encoding="utf-8"
            )
            (run_dir / "initial_investigation_final.md").write_text(
                "Observed local evidence.", encoding="utf-8"
            )
            with patch("controller.web_api.config.ARTIFACTS_ROOT", Path(directory) / "artifacts"):
                snapshot = live_run_snapshot()

        self.assertTrue(snapshot["available"])
        self.assertEqual(snapshot["status"], "approval_pending")
        self.assertTrue(snapshot["session"]["connected"])
        self.assertEqual(snapshot["target"]["health"]["body"]["version"], "target-v2")
        self.assertNotEqual(snapshot["session"]["session_id"], "sess_test")
        self.assertEqual(snapshot["session"]["session_id"], "sess_…[redacted]")
        self.assertEqual(snapshot["session"]["environment_id"], "env_…[redacted]")
        self.assertIn("agent.session.turn.completed", snapshot["agent_event_type_counts"])
        self.assertFalse(snapshot["proposal"]["mutation_executed"])

    def test_local_console_is_explicitly_not_connected_to_agent_api(self) -> None:
        console = LocalConsole()
        snapshot = console.snapshot()
        self.assertEqual(snapshot["mode"], "local_deterministic")
        self.assertEqual(snapshot["agent"]["status"], "not_connected")
        self.assertIsNone(snapshot["agent"]["session_id"])

    def test_proposal_is_controller_owned_and_allowlisted(self) -> None:
        console = LocalConsole()
        console.state["run_id"] = "run-test"
        proposal = console._proposal()
        self.assertEqual(proposal["source"], "controller_demo")
        self.assertEqual(proposal["action_id"], "restore_known_safe_runtime_config")
        self.assertIn("target container only", proposal["scope"])

    def test_evidence_reader_rejects_paths_outside_allowlist(self) -> None:
        console = LocalConsole()
        with self.assertRaises(HTTPException) as context:
            console.docker_read("/etc/passwd")
        self.assertEqual(context.exception.status_code, 400)

    def test_approval_requires_current_proposal_and_explicit_decision(self) -> None:
        console = LocalConsole()
        console.state["run_id"] = "run-test"
        console.state["phase"] = "approval_required"
        console.state["proposal"] = console._proposal()
        proposal_id = console.state["proposal"]["id"]

        result = console.approve(ApprovalRequest(decision="deny", proposal_id=proposal_id))

        self.assertEqual(result["phase"], "approval_denied")
        self.assertFalse(result["approval"]["approved"])

    def test_approval_cannot_be_inferred_from_missing_or_wrong_proposal(self) -> None:
        console = LocalConsole()
        with self.assertRaises(HTTPException):
            console.approve(ApprovalRequest(decision="approve", proposal_id="missing"))

    def test_approval_is_not_recorded_while_incident_worker_is_still_running(self) -> None:
        console = LocalConsole()
        console.state["run_id"] = "run-test"
        console.state["phase"] = "approval_required"
        console.state["proposal"] = console._proposal()
        proposal_id = console.state["proposal"]["id"]
        worker = Mock()
        worker.is_alive.return_value = True
        console.worker = worker

        with self.assertRaises(HTTPException) as context:
            console.approve(ApprovalRequest(decision="approve", proposal_id=proposal_id))

        self.assertEqual(context.exception.status_code, 409)
        self.assertIsNone(console.snapshot()["approval"])
        self.assertEqual(console.snapshot()["phase"], "approval_required")
        worker.join.assert_called_once_with(timeout=2)

    @patch("controller.web_api.apply_known_safe_remediation")
    @patch("controller.web_api.snapshot_runtime")
    @patch("controller.web_api.wait_for_health", return_value={"status": 200})
    @patch("controller.web_api.request_json")
    def test_remediation_preserves_incident_checkout_for_before_after_evidence(
        self,
        request_json,
        wait_for_health,
        snapshot_runtime,
        apply_remediation,
    ) -> None:
        request_json.side_effect = [
            {"status": 200, "body": {"status": "approved"}},
            {"status": 200, "body": {"checkout_timeouts": 0}},
        ]
        console = LocalConsole()
        incident = {
            "label": "checkout_3",
            "status": 504,
            "body": {"error_code": "checkout_dependency_timeout"},
        }
        console.state["target"]["last_checkout"] = incident
        console.state["target"]["incident_checkout"] = incident
        with tempfile.TemporaryDirectory() as directory:
            console.run_dir = Path(directory)
            console.capture = EventCapture(console.run_dir)
            console._run_remediation()

        snapshot = console.snapshot()
        self.assertEqual(snapshot["target"]["incident_checkout"]["status"], 504)
        self.assertEqual(snapshot["target"]["verification_checkout"]["status"], 200)
        self.assertEqual(snapshot["target"]["last_checkout"]["status"], 200)
        self.assertTrue(snapshot["verification"]["verified"])
        apply_remediation.assert_called_once_with(console.capture, approved=True)

    @patch("controller.web_api.request_json")
    def test_payment_simulation_uses_only_fixed_checkout_operation(self, request_json) -> None:
        request_json.side_effect = [
            {
                "path": "/checkout",
                "status": 504,
                "body": {
                    "request_id": "synthetic-request",
                    "error_code": "checkout_dependency_timeout",
                },
            },
            {"path": "/metrics", "status": 200, "body": {"checkout_timeouts": 1}},
        ]
        console = LocalConsole()

        result = console.simulate_payment()

        request_json.assert_any_call(
            "/checkout",
            method="POST",
            body={"order_id": "ui-demo-order", "amount_cents": 1099},
        )
        self.assertEqual(result["checkout"]["status"], 504)
        self.assertEqual(console.snapshot()["target"]["last_checkout"]["label"], "ui_simulated_checkout")


if __name__ == "__main__":
    unittest.main()
