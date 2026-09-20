"""Redacted, append-only event and identity capture."""

from __future__ import annotations

import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

SECRET_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{8,}|(?:key|token|secret)[-_][A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~-]{8,})",
    re.IGNORECASE,
)
SENSITIVE_KEYS = {
    "authorization",
    "api_key",
    "apikey",
    "codex_api_key",
    "environment_key",
    "executor_api_key",
    "openai_api_key",
    "openai_executor_api_key",
    "password",
    "remote_url",
    "secret",
    "signed_url",
    "token",
}


def redact(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for item_key, item in value.items():
            normalized_key = str(item_key).lower().replace("-", "_")
            if normalized_key in SENSITIVE_KEYS or normalized_key.endswith("_token"):
                redacted[str(item_key)] = "[REDACTED]"
            else:
                redacted[str(item_key)] = redact(item, normalized_key)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        if key in SENSITIVE_KEYS:
            return "[REDACTED]"
        return SECRET_PATTERN.sub("[REDACTED]", value)
    return value


class EventCapture:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.started = time.monotonic()
        self.controller_path = run_dir / "controller_events.jsonl"
        self.agent_path = run_dir / "agents_api_events.jsonl"

    def _append(self, path: Path, kind: str, payload: Any) -> None:
        record = {
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_ms": round((time.monotonic() - self.started) * 1000, 3),
            "kind": kind,
            "payload": redact(payload),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def controller(self, kind: str, payload: Any) -> None:
        self._append(self.controller_path, kind, payload)

    def agent_event(self, payload: Any, raw_event_name: str | None = None) -> None:
        self._append(
            self.agent_path,
            "agents_api_event",
            {"raw_event_name": raw_event_name, "event": payload},
        )

    def write_json(self, name: str, payload: Any) -> None:
        (self.run_dir / name).write_text(
            json.dumps(redact(payload), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def write_text(self, name: str, content: str) -> None:
        (self.run_dir / name).write_text(content, encoding="utf-8")


def git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=config.REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "uncommitted-or-unavailable"
    return result.stdout.strip()


def runtime_identity(
    session_id: str | None = None,
    agent_id: str | None = None,
    environment_id: str | None = None,
) -> dict[str, object]:
    identity: dict[str, object] = {
        "git_commit": git_commit(),
        "experiment": "armie-operational-intelligence",
        "experiment_version": config.EXPERIMENT_VERSION,
        "target_service_version": config.TARGET_SERVICE_VERSION,
        "deployment_version": config.DEPLOYMENT_VERSION,
        "configured_model": config.MODEL,
        "environment_type": config.ENVIRONMENT_TYPE,
    }
    if agent_id:
        identity["agent_id"] = agent_id
    if session_id:
        identity["agents_api_session_id"] = session_id
    if environment_id:
        identity["agents_api_environment_id"] = environment_id
    return identity
