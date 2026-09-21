from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from controller.config import (
    credential_presence,
    require_executor_api_key,
    require_openai_api_key,
    require_runtime_identifiers,
    session_payload,
)
from controller.events import EventCapture, redact
from controller.remediation import (
    ApprovalRequired,
    apply_known_safe_remediation,
    approval_from_text,
    require_approval,
)
from controller.cli import extract_final_assistant_text
from controller.runner import ExecutorProcess


class ControllerTests(unittest.TestCase):
    def test_openai_key_validation_uses_only_named_variable(self) -> None:
        with self.assertRaises(RuntimeError):
            require_openai_api_key({})
        self.assertEqual(require_openai_api_key({"OPENAI_API_KEY": "test-key"}), "test-key")

    def test_executor_key_is_separate_and_presence_only(self) -> None:
        env = {
            "OPENAI_API_KEY": "application-key",
            "OPENAI_EXECUTOR_API_KEY": "executor-key",
        }
        self.assertEqual(require_executor_api_key(env), "executor-key")
        self.assertEqual(
            credential_presence(env),
            {
                "OPENAI_API_KEY": "present",
                "OPENAI_EXECUTOR_API_KEY": "present",
            },
        )
        self.assertEqual(credential_presence({})["OPENAI_API_KEY"], "missing")
        self.assertEqual(credential_presence({})["OPENAI_EXECUTOR_API_KEY"], "missing")

    def test_executor_environment_excludes_application_credential(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "OPENAI_API_KEY": "application-key",
                "OPENAI_EXECUTOR_API_KEY": "executor-key",
                "UNRELATED_SETTING": "retained",
            },
            clear=True,
        ):
            child = ExecutorProcess.executor_environment("https://remote.invalid", "env_test")
        self.assertEqual(child["CODEX_API_KEY"], "executor-key")
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertNotIn("OPENAI_EXECUTOR_API_KEY", child)
        self.assertEqual(child["SESSION_REMOTE_URL"], "https://remote.invalid")

    def test_session_configuration_references_saved_agent_and_override(self) -> None:
        payload = session_payload("saved-agent-reference", "project-reference")
        self.assertEqual(payload["agent_id"], "saved-agent-reference")
        self.assertEqual(payload["agent"]["model"], "gpt-5.6-luna")
        self.assertEqual(payload["environment"]["type"], "self_hosted")
        self.assertEqual(payload["environment"]["workspace_directory"], "/workspace")
        self.assertEqual(payload["metadata"]["openai_project_id"], "project-reference")

    def test_runtime_identifiers_are_required_from_environment(self) -> None:
        self.assertEqual(
            require_runtime_identifiers(
                {"ARMIE_SRE_AGENT_ID": "saved", "OPENAI_PROJECT_ID": "project"}
            ),
            ("saved", "project"),
        )
        with self.assertRaises(RuntimeError):
            require_runtime_identifiers({})

    def test_approval_defaults_to_denied(self) -> None:
        self.assertFalse(approval_from_text(""))
        self.assertFalse(approval_from_text("N"))
        self.assertTrue(approval_from_text("y"))

    def test_remediation_cannot_execute_without_approval(self) -> None:
        with self.assertRaises(ApprovalRequired):
            require_approval(False)
        with tempfile.TemporaryDirectory() as directory:
            capture = EventCapture(Path(directory))
            with patch("controller.remediation.subprocess.run") as run:
                with self.assertRaises(ApprovalRequired):
                    apply_known_safe_remediation(capture, approved=False)
                run.assert_not_called()
        require_approval(True)

    def test_artifact_persistence_and_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capture = EventCapture(Path(directory))
            capture.controller(
                "test",
                {
                    "token": "test-token-placeholder",
                    "Authorization": "Bearer test-placeholder",
                    "remote_url": "https://executor.invalid?signature=secret",
                },
            )
            content = (Path(directory) / "controller_events.jsonl").read_text()
            self.assertIn("[REDACTED]", content)
            self.assertNotIn("test-token-placeholder", content)
            self.assertNotIn("executor.invalid", content)
            capture.write_text(
                "turn_final.md",
                "Authorization: Bearer test-placeholder "
                "https://executor.invalid/connect?signature=secret",
            )
            text_content = (Path(directory) / "turn_final.md").read_text()
            self.assertNotIn("test-placeholder", text_content)
            self.assertNotIn("executor.invalid", text_content)

    def test_free_text_redaction_scrubs_signed_urls_and_assignments(self) -> None:
        sanitized = redact(
            "remote=https://executor.invalid/connect?signature=secret&expires=123 "
            "OPENAI_EXECUTOR_API_KEY=ordinary-looking-value"
        )
        self.assertNotIn("executor.invalid", sanitized)
        self.assertNotIn("ordinary-looking-value", sanitized)
        self.assertIn("[REDACTED_SIGNED_URL]", sanitized)

    def test_final_text_comes_from_completed_assistant_item(self) -> None:
        items = {
            "data": [
                {"type": "agent_command_execution", "output_text": "tool output"},
                {
                    "type": "agent_session_assistant_message",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": "final answer"}],
                },
            ]
        }
        self.assertEqual(extract_final_assistant_text(items), "final answer")

    def test_incomplete_assistant_item_is_not_final_text(self) -> None:
        items = {
            "data": [
                {
                    "role": "assistant",
                    "status": "incomplete",
                    "content": [{"type": "output_text", "text": "partial"}],
                }
            ]
        }
        self.assertIsNone(extract_final_assistant_text(items))

    def test_approved_remediation_clears_reset_flag_before_recreate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capture = EventCapture(Path(directory))
            with patch("controller.remediation.config.RUNTIME_ROOT", Path(directory)), patch(
                "controller.remediation.config.REPO_ROOT", Path(directory)
            ), patch("controller.remediation.subprocess.run") as run:
                run.side_effect = [
                    Mock(returncode=0, stdout="target-id\n", stderr=""),
                    Mock(returncode=0, stdout="", stderr=""),
                    Mock(returncode=0, stdout="started\n", stderr=""),
                ]
                apply_known_safe_remediation(capture, approved=True)
                recreate_call = run.call_args_list[-1]
                self.assertEqual(recreate_call.kwargs["env"]["RESET_RUNTIME_CONFIG"], "0")
                self.assertIn("--force-recreate", recreate_call.args[0])

    def test_redaction_removes_credential_fields_not_just_key_patterns(self) -> None:
        sanitized = redact({"OPENAI_API_KEY": "ordinary-looking-value", "safe": "value"})
        self.assertEqual(sanitized["OPENAI_API_KEY"], "[REDACTED]")
        self.assertEqual(sanitized["safe"], "value")
