from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from controller.config import require_openai_api_key, session_payload
from controller.events import EventCapture
from controller.remediation import ApprovalRequired, approval_from_text, require_approval


class ControllerTests(unittest.TestCase):
    def test_openai_key_validation_uses_only_named_variable(self) -> None:
        with self.assertRaises(RuntimeError):
            require_openai_api_key({})
        self.assertEqual(require_openai_api_key({"OPENAI_API_KEY": "test-key"}), "test-key")

    def test_session_configuration_references_saved_agent_and_override(self) -> None:
        payload = session_payload()
        self.assertEqual(
            payload["agent_id"],
            "agent_8041a399c9434e048f081b847bd11b74bf6e735fde2f4685a4",
        )
        self.assertEqual(payload["agent"]["model"], "gpt-5.6-luna")
        self.assertEqual(payload["environment"]["type"], "self_hosted")

    def test_approval_defaults_to_denied(self) -> None:
        self.assertFalse(approval_from_text(""))
        self.assertFalse(approval_from_text("N"))
        self.assertTrue(approval_from_text("y"))

    def test_remediation_cannot_execute_without_approval(self) -> None:
        with self.assertRaises(ApprovalRequired):
            require_approval(False)
        require_approval(True)

    def test_artifact_persistence_and_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capture = EventCapture(Path(directory))
            capture.controller("test", {"token": "sk-secret-value-123456"})
            content = (Path(directory) / "controller_events.jsonl").read_text()
            self.assertIn("[REDACTED]", content)
            self.assertNotIn("sk-secret-value-123456", content)

