from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from controller.web_api import ApprovalRequest, LocalConsole, live_run_snapshot


class WebConsoleContractTests(unittest.TestCase):
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
