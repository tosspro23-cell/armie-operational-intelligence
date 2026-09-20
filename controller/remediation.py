"""The only mutation exposed by the spike, guarded by explicit approval."""

from __future__ import annotations

import json
import subprocess
from typing import Any

from . import config
from .events import EventCapture


class ApprovalRequired(RuntimeError):
    pass


def approval_from_text(value: str) -> bool:
    return value.strip().lower() in {"y", "yes"}


def require_approval(approved: bool) -> None:
    if not approved:
        raise ApprovalRequired("remediation requires explicit human approval")


def apply_known_safe_remediation(capture: EventCapture, approved: bool) -> None:
    """Restore only the checked-in safe fixture and restart only target."""

    require_approval(approved)
    safe_path = config.FIXTURES_ROOT / "runtime_config_safe.json"
    destination = config.RUNTIME_ROOT / "runtime_config.json"
    safe_config: dict[str, Any] = json.loads(safe_path.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(safe_config, indent=2) + "\n", encoding="utf-8")
    container_result = subprocess.run(
        ["docker", "compose", "-f", str(config.COMPOSE_FILE), "ps", "-q", "target"],
        cwd=config.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    container_id = container_result.stdout.strip()
    if container_result.returncode != 0 or not container_id:
        raise RuntimeError("could not resolve target container for approved remediation")
    copy_result = subprocess.run(
        ["docker", "cp", str(destination), f"{container_id}:/app/shared/runtime_config.json"],
        cwd=config.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if copy_result.returncode != 0:
        raise RuntimeError(f"could not stage approved safe config: {copy_result.stderr.strip()}")
    capture.controller(
        "remediation_config_restored",
        {
            "action": "restore_checked_in_safe_runtime_config",
            "destination": str(destination.relative_to(config.REPO_ROOT)),
            "target_service": "synthetic-payment-api",
            "container_id": container_id,
        },
    )
    result = subprocess.run(
        ["docker", "compose", "-f", str(config.COMPOSE_FILE), "restart", "target"],
        cwd=config.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    capture.controller(
        "remediation_restart",
        {
            "action": "restart_target_only",
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode != 0:
        raise RuntimeError(f"controlled target restart failed: {result.stderr.strip()}")
