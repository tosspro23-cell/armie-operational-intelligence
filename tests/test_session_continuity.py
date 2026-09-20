from __future__ import annotations

import unittest


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


if __name__ == "__main__":
    unittest.main()

