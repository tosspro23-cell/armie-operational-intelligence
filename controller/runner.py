"""Session lifecycle, self-hosted executor, and human-gated workflow."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import threading
import time
from typing import Any

from . import config
from .api import AgentApiClient, AgentApiError
from .events import EventCapture, runtime_identity


def event_type(payload: Any) -> str | None:
    if isinstance(payload, dict):
        value = payload.get("type")
        if isinstance(value, str):
            return value
    return None


class StreamMonitor:
    def __init__(self, client: AgentApiClient, session_id: str, capture: EventCapture) -> None:
        self.client = client
        self.session_id = session_id
        self.capture = capture
        self.events: queue.Queue[tuple[str | None, Any]] = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.error: Exception | None = None
        self.opened = threading.Event()
        self.seen: list[tuple[str | None, Any]] = []

    def start(self) -> None:
        self.thread.start()

    def _read(self) -> None:
        try:
            for raw_name, payload in self.client.stream_events(
                self.session_id, on_open=self.opened.set
            ):
                self.capture.agent_event(payload, raw_name)
                self.seen.append((raw_name, payload))
                self.events.put((raw_name, payload))
                if self.stop_event.is_set():
                    break
        except Exception as exc:
            self.error = exc
            self.capture.controller("stream_error", {"error": str(exc)})
            self.events.put((None, {"type": "controller.stream_error", "error": str(exc)}))
        finally:
            self.events.put((None, {"type": "controller.stream_closed"}))

    def stop(self) -> None:
        self.stop_event.set()
        self.thread.join(timeout=2)


class ExecutorProcess:
    def __init__(self, capture: EventCapture) -> None:
        self.capture = capture
        self.process: subprocess.Popen[bytes] | None = None
        self.log_handle: Any = None

    def start(self, session: dict[str, Any]) -> None:
        environment = session.get("environment") or {}
        remote_url = environment.get("remote_url")
        environment_id = environment.get("id")
        if not isinstance(remote_url, str) or not isinstance(environment_id, str):
            raise RuntimeError(
                "session did not return self-hosted environment id and remote_url"
            )
        log_path = self.capture.run_dir / "executor.log"
        self.log_handle = log_path.open("ab")
        child_env = self.executor_environment(remote_url, environment_id)
        command = [
            "docker",
            "compose",
            "-f",
            str(config.COMPOSE_FILE),
            "run",
            "--rm",
            "--no-deps",
            "-e",
            "CODEX_API_KEY",
            "-e",
            "SESSION_REMOTE_URL",
            "-e",
            "SESSION_ENVIRONMENT_ID",
            "sre_environment",
        ]
        self.capture.controller(
            "executor_starting",
            {
                "command": command,
                "environment_id": environment_id,
                "remote_url_present": True,
                "passed_environment_names": [
                    "CODEX_API_KEY",
                    "SESSION_REMOTE_URL",
                    "SESSION_ENVIRONMENT_ID",
                ],
            },
        )
        self.process = subprocess.Popen(
            command,
            cwd=config.REPO_ROOT,
            env=child_env,
            stdout=self.log_handle,
            stderr=subprocess.STDOUT,
        )

    @staticmethod
    def executor_environment(remote_url: str, environment_id: str) -> dict[str, str]:
        """Build a minimal child environment without leaking the app key."""

        child_env = os.environ.copy()
        executor_key = child_env.pop("OPENAI_EXECUTOR_API_KEY", "")
        child_env.pop("OPENAI_API_KEY", None)
        child_env.pop("CODEX_API_KEY", None)
        if not executor_key:
            raise RuntimeError("OPENAI_EXECUTOR_API_KEY is required for executor startup")
        child_env["CODEX_API_KEY"] = executor_key
        child_env["SESSION_REMOTE_URL"] = remote_url
        child_env["SESSION_ENVIRONMENT_ID"] = environment_id
        return child_env

    def ensure_alive(self) -> None:
        if self.process is None:
            raise RuntimeError("executor has not been started")
        if self.process.poll() is not None:
            raise RuntimeError(f"executor exited with code {self.process.returncode}")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        if self.log_handle is not None:
            self.log_handle.close()


class SessionRunner:
    def __init__(self, client: AgentApiClient, capture: EventCapture, session: dict[str, Any]) -> None:
        self.client = client
        self.capture = capture
        self.session = session
        self.session_id = str(session["id"])
        self.executor = ExecutorProcess(capture)

    def start_executor(self) -> None:
        self.executor.start(self.session)
        environment = self.session.get("environment", {})
        agent = self.session.get("agent", {})
        self.capture.write_json(
            "runtime_identity.json",
            runtime_identity(
                self.session_id,
                agent.get("id") if isinstance(agent, dict) else None,
                environment.get("id") if isinstance(environment, dict) else None,
            ),
        )

    def _next_event(self, monitor: StreamMonitor, timeout: float) -> Any:
        try:
            _, payload = monitor.events.get(timeout=timeout)
            return payload
        except queue.Empty as exc:
            monitor.stop()
            self.executor.ensure_alive()
            raise TimeoutError("timed out waiting for Agents API event") from exc

    def _wait_connected(self, monitor: StreamMonitor, timeout: float = 180.0) -> None:
        if not monitor.opened.wait(timeout=30):
            raise TimeoutError("event stream did not open before sending work")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            payload = self._next_event(monitor, min(5.0, deadline - time.monotonic()))
            kind = event_type(payload)
            if kind == "agent.session.environment.connected":
                self.capture.controller("environment_connected", {})
                return
            if kind in {"agent.session.environment.failed", "error"}:
                raise AgentApiError("environment connection", None, json.dumps(payload))
            if kind == "controller.stream_error":
                raise RuntimeError(str(payload))
        raise TimeoutError("self-hosted executor did not connect before timeout")

    def _wait_turn_completed(
        self,
        monitor: StreamMonitor,
        timeout: float = 900.0,
    ) -> tuple[str, Any]:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            payload = self._next_event(monitor, min(10.0, deadline - time.monotonic()))
            kind = event_type(payload)
            if kind == "agent.session.turn.completed":
                self.capture.controller(
                    "turn_completed",
                    {"session_id": self.session_id, "outcome": "completed"},
                )
                return "completed", payload
            if kind in {
                "agent.session.turn.failed",
                "agent.session.failed",
                "agent.session.turn.cancelled",
                "error",
            }:
                outcome = "cancelled" if "cancel" in (kind or "") else "failed"
                self.capture.controller(
                    "turn_completed",
                    {"session_id": self.session_id, "outcome": outcome},
                )
                raise AgentApiError("agent turn", None, json.dumps(payload))
            if kind == "controller.stream_error":
                raise RuntimeError(str(payload))
        raise TimeoutError("agent turn did not complete before timeout")

    def run_turn(
        self,
        label: str,
        message: str,
        wait_for_connection: bool = False,
    ) -> dict[str, Any]:
        monitor = StreamMonitor(self.client, self.session_id, self.capture)
        monitor.start()
        try:
            if wait_for_connection:
                self._wait_connected(monitor)
            else:
                if not monitor.opened.wait(timeout=30):
                    raise TimeoutError("event stream did not open before follow-up")
                self.executor.ensure_alive()
            self.capture.controller(
                "session_input",
                {"session_id": self.session_id, "label": label, "message": message},
            )
            self.client.send_message(self.session_id, message)
            outcome, terminal_event = self._wait_turn_completed(monitor)
            session_state = self.client.retrieve_session(self.session_id)
            items = self.client.list_items(self.session_id)
            self.capture.write_json(f"{label}_items.json", items)
            self.capture.controller(
                "session_state_retrieved",
                {
                    "session_id": self.session_id,
                    "status": session_state.get("status"),
                    "required_actions": session_state.get("required_actions"),
                },
            )
            self.capture.controller(
                "session_items_retrieved",
                {
                    "session_id": self.session_id,
                    "label": label,
                    "item_count": len(items.get("data", []))
                    if isinstance(items.get("data"), list)
                    else None,
                },
            )
            return {
                "label": label,
                "session_id": self.session_id,
                "outcome": outcome,
                "terminal_event": terminal_event,
                "events": list(monitor.seen),
            }
        finally:
            monitor.stop()

    def stop(self) -> None:
        self.executor.stop()
