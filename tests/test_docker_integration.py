"""Opt-in Docker proof for the approved remediation lifecycle."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from controller import config
from controller.events import EventCapture
from controller.probe import request_json, wait_for_health
from controller.remediation import apply_known_safe_remediation


@unittest.skipUnless(
    os.environ.get("ARMIE_RUN_DOCKER_INTEGRATION") == "1",
    "set ARMIE_RUN_DOCKER_INTEGRATION=1 to run the real Docker remediation proof",
)
class DockerRemediationIntegrationTests(unittest.TestCase):
    def _compose(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        child_env = dict(os.environ)
        if env:
            child_env.update(env)
        return subprocess.run(
            ["docker", "compose", "-f", str(config.COMPOSE_FILE), *args],
            cwd=config.REPO_ROOT,
            env=child_env,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )

    def test_fault_then_approved_remediation_survives_target_restart(self) -> None:
        start = self._compose(
            "up",
            "-d",
            "--build",
            "--force-recreate",
            "target",
            env={"RESET_RUNTIME_CONFIG": "1"},
        )
        self.assertEqual(start.returncode, 0, start.stderr)
        try:
            wait_for_health()
            fault = request_json(
                "/checkout",
                method="POST",
                body={"order_id": "integration-fault", "amount_cents": 1099},
            )
            self.assertEqual(fault["status"], 504, fault)

            with tempfile.TemporaryDirectory() as directory:
                capture = EventCapture(Path(directory))
                apply_known_safe_remediation(capture, approved=True)

            wait_for_health()
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                recovered = request_json(
                    "/checkout",
                    method="POST",
                    body={"order_id": "integration-recovered", "amount_cents": 1099},
                )
                if recovered["status"] == 200:
                    break
                time.sleep(1)
            self.assertEqual(recovered["status"], 200, recovered)
        finally:
            stopped = self._compose("stop", "target")
            self.assertEqual(stopped.returncode, 0, stopped.stderr)
