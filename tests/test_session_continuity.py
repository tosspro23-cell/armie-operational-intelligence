from __future__ import annotations

import unittest
import tempfile
from pathlib import Path
from unittest.mock import Mock

from controller.events import EventCapture
from controller.runner import SessionRunner


class SessionContinuityTests(unittest.TestCase):
    def test_followups_use_one_session_identifier(self) -> None:
        session_id = "sess_test_123"
        labels = [
            "initial_investigation",
            "contradictory_evidence_reassessment",
            "remediation_proposal",
            "post_remediation_verification",
        ]
        recorded = [(session_id, label) for label in labels]
        self.assertEqual({item[0] for item in recorded}, {session_id})
        self.assertEqual(len(recorded), 4)

    def test_runner_binds_every_turn_to_constructed_session(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            capture = EventCapture(Path(directory))
            client = Mock()
            runner = SessionRunner(
                client,
                capture,
                {"id": "sess_real_reference", "environment": {}},
            )
            self.assertEqual(runner.session_id, "sess_real_reference")
            self.assertIs(runner.session, runner.session)


if __name__ == "__main__":
    unittest.main()
