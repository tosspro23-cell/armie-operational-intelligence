"""Local-only FastAPI presentation and control API for the SRE console.

This module is a thin adapter over the existing deterministic controller. It
does not create an Agent, expose arbitrary commands, or replace the Agents API
session runner. The browser receives sanitized state and lifecycle events only.
"""

from __future__ import annotations

import asyncio
import json
import queue
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from . import config
from .cli import (
    compose_stop,
    compose_up,
    new_run,
    prepare_runtime,
    validate_executor_boundary,
)
from .events import EventCapture, redact, runtime_identity
from .probe import (
    probe_incident,
    request_json,
    snapshot_runtime,
    wait_for_health,
    write_probe_artifact,
)
from .remediation import apply_known_safe_remediation


class ApprovalRequest(BaseModel):
    decision: Literal["approve", "deny"]
    proposal_id: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LocalConsole:
    """Own the first-slice local validation lifecycle and its browser events."""

    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.worker: threading.Thread | None = None
        self.capture: EventCapture | None = None
        self.run_dir: Path | None = None
        self.subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self.events: list[dict[str, Any]] = []
        self.state: dict[str, Any] = {
            "mode": "local_deterministic",
            "phase": "idle",
            "run_id": None,
            "started_at": None,
            "updated_at": utc_now(),
            "identity": runtime_identity(),
            "target": {
                "base_url": config.TARGET_BASE_URL,
                "health": None,
                "metrics": None,
                "downstream": None,
                "timeline": None,
                "last_checkout": None,
            },
            "agent": {
                "status": "not_connected",
                "session_id": None,
                "environment_id": None,
                "message": "Agent API is not connected in local deterministic mode.",
            },
            "proposal": None,
            "approval": None,
            "verification": None,
            "error": None,
        }

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return json.loads(json.dumps(self.state))

    def event_snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            return json.loads(json.dumps(self.events[-200:]))

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue()
        with self.lock:
            self.subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self.lock:
            self.subscribers.discard(subscriber)

    def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        record = {
            "id": len(self.events) + 1,
            "type": event_type,
            "captured_at": utc_now(),
            "payload": redact(payload),
        }
        with self.lock:
            self.events.append(record)
            if self.capture is not None:
                self.capture.controller(event_type, payload)
            for subscriber in list(self.subscribers):
                subscriber.put(record)
            if self.run_dir is not None:
                path = self.run_dir / "ui_events.jsonl"
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, sort_keys=True) + "\n")

    def set_state(self, **changes: Any) -> None:
        with self.lock:
            self.state.update(changes)
            self.state["updated_at"] = utc_now()
            phase = self.state.get("phase")
        self.emit("ui.state.changed", {"phase": phase})

    def _active(self) -> bool:
        return self.worker is not None and self.worker.is_alive()

    def _launch(self, target: Any) -> dict[str, Any]:
        with self.lock:
            if self._active():
                raise HTTPException(status_code=409, detail="a local operation is already running")
            self.worker = threading.Thread(target=target, daemon=True)
            self.worker.start()
        return self.snapshot()

    def start_local(self) -> dict[str, Any]:
        return self._launch(self._run_local)

    def reset_local(self) -> dict[str, Any]:
        return self._launch(self._run_local)

    def _begin_run(self) -> None:
        run_dir, capture = new_run()
        with self.lock:
            self.run_dir = run_dir
            self.capture = capture
            self.events = []
            self.state = {
                **self.state,
                "phase": "target_starting",
                "run_id": run_dir.name,
                "started_at": utc_now(),
                "updated_at": utc_now(),
                "identity": runtime_identity(),
                "proposal": None,
                "approval": None,
                "verification": None,
                "error": None,
                "target": {
                    "base_url": config.TARGET_BASE_URL,
                    "health": None,
                    "metrics": None,
                    "downstream": None,
                    "timeline": None,
                    "last_checkout": None,
                },
            }
            capture.controller("ui_run_started", {"run_id": run_dir.name})
            capture.write_json("runtime_identity.json", runtime_identity())
        self.emit("ui.run.started", {"run_id": run_dir.name})

    def _run_local(self) -> None:
        self._begin_run()
        try:
            prepare_runtime()
            compose_up(force_recreate=True)
            health = wait_for_health()
            with self.lock:
                self.state["target"]["health"] = health
            self.emit("target.health.observed", health)

            validate_executor_boundary(self.capture)  # type: ignore[arg-type]
            self.emit("executor.boundary.verified", {"read_only": True})

            probes = probe_incident(self.capture)  # type: ignore[arg-type]
            write_probe_artifact(self.run_dir, probes)  # type: ignore[arg-type]
            snapshot_runtime(self.run_dir)  # type: ignore[arg-type]
            timeline = request_json("/diagnostics/timeline")
            with self.lock:
                self.state["target"]["metrics"] = request_json("/metrics")
                self.state["target"]["downstream"] = request_json("/diagnostics/downstream")
                self.state["target"]["timeline"] = timeline
                self.state["target"]["last_checkout"] = next(
                    (item for item in reversed(probes) if item["label"].startswith("checkout_")),
                    None,
                )
                self.state["phase"] = "approval_required"
                self.state["proposal"] = self._proposal()
            self.emit("incident.reproduced", {"checkout_status": 504})
            self.emit("contradictory.evidence.available", timeline)
            self.emit("approval.required", self.snapshot()["proposal"])
        except Exception as exc:
            safe_error = str(redact(str(exc)))
            self.set_state(phase="failed", error=safe_error)
            self.emit("ui.run.failed", {"error_type": type(exc).__name__, "error": safe_error})

    def _proposal(self) -> dict[str, Any]:
        return {
            "id": f"{self.state['run_id']}:restore-known-safe-config",
            "source": "controller_demo",
            "action_id": "restore_known_safe_runtime_config",
            "title": "Restore the checked-in safe runtime configuration",
            "scope": "synthetic-payment-api target container only",
            "risks": [
                "The target container will be recreated with the known-safe fixture.",
                "This is local synthetic state and does not affect production.",
            ],
            "verification_plan": [
                "Wait for /health to return 200.",
                "Send a new POST /checkout and require HTTP 200.",
                "Read new metrics and structured logs.",
            ],
            "rollback_plan": "Reset the target with the deterministic fault fixture.",
        }

    def approve(self, request: ApprovalRequest) -> dict[str, Any]:
        with self.lock:
            proposal = self.state.get("proposal")
            if self.state.get("phase") != "approval_required" or not proposal:
                raise HTTPException(status_code=409, detail="no approval is currently required")
            if request.proposal_id != proposal["id"]:
                raise HTTPException(status_code=409, detail="proposal identifier does not match")
            approved = request.decision == "approve"
            self.state["approval"] = {
                "decision": request.decision,
                "approved": approved,
                "recorded_at": utc_now(),
            }
            self.state["phase"] = "remediation_running" if approved else "approval_denied"
        self.emit("approval.recorded", self.snapshot()["approval"])
        if not approved:
            self.emit("remediation.denied", {"reason": "explicit human denial"})
            return self.snapshot()
        return self._launch(self._run_remediation)

    def _run_remediation(self) -> None:
        try:
            apply_known_safe_remediation(self.capture, approved=True)  # type: ignore[arg-type]
            health = wait_for_health()
            checkout = request_json(
                "/checkout",
                method="POST",
                body={"order_id": "ui-recovery-check", "amount_cents": 1099},
            )
            metrics = request_json("/metrics")
            snapshot_runtime(self.run_dir)  # type: ignore[arg-type]
            with self.lock:
                self.state["target"]["health"] = health
                self.state["target"]["last_checkout"] = checkout
                self.state["target"]["metrics"] = metrics
                self.state["verification"] = {
                    "health": health,
                    "checkout": checkout,
                    "metrics": metrics,
                    "verified": checkout.get("status") == 200,
                }
                self.state["phase"] = (
                    "verification_complete" if checkout.get("status") == 200 else "verification_failed"
                )
            self.emit("remediation.applied", {"action_id": "restore_known_safe_runtime_config"})
            self.emit("verification.completed", self.snapshot()["verification"])
        except Exception as exc:
            safe_error = str(redact(str(exc)))
            self.set_state(phase="failed", error=safe_error)
            self.emit("remediation.failed", {"error_type": type(exc).__name__, "error": safe_error})

    def stop_local(self) -> dict[str, Any]:
        with self.lock:
            if self._active():
                raise HTTPException(status_code=409, detail="a local operation is still running")
        compose_stop()
        self.set_state(phase="idle")
        self.emit("target.stopped", {"target": "synthetic-payment-api"})
        return self.snapshot()

    def docker_read(self, path: str) -> str:
        allowed = {
            "/app/shared/service.jsonl",
            "/app/shared/runtime_config.json",
            "/app/metadata/deployment.json",
            "/app/runbook/runbook.md",
        }
        if path not in allowed:
            raise HTTPException(status_code=400, detail="evidence path is not allowlisted")
        result = subprocess.run(
            ["docker", "compose", "-f", str(config.COMPOSE_FILE), "exec", "-T", "target", "cat", path],
            cwd=config.REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            raise HTTPException(status_code=503, detail="target evidence is unavailable")
        return result.stdout


console = LocalConsole()
app = FastAPI(title="ARMIE SRE Local Console", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.get("/api/health")
def backend_health() -> dict[str, Any]:
    try:
        target = request_json("/health")
    except Exception:
        target = None
    return {
        "status": "ok",
        "mode": "local_deterministic",
        "target_reachable": target is not None and target.get("status") == 200,
        "agent_api": "not_connected",
    }


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    return console.snapshot()


@app.get("/api/events")
def get_events() -> dict[str, Any]:
    return {"data": console.event_snapshot()}


@app.get("/api/events/stream")
async def stream_events() -> StreamingResponse:
    subscriber = console.subscribe()

    async def event_generator():
        try:
            initial = {"type": "snapshot", "data": console.snapshot()}
            yield f"event: snapshot\ndata: {json.dumps(initial, sort_keys=True)}\n\n"
            while True:
                try:
                    record = await asyncio.to_thread(subscriber.get, True, 15)
                    yield f"event: {record['type']}\ndata: {json.dumps(record, sort_keys=True)}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            console.unsubscribe(subscriber)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/evidence/logs")
def get_logs(limit: int = 80) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    raw = console.docker_read("/app/shared/service.jsonl")
    lines = [line for line in raw.splitlines() if line.strip()][-limit:]
    records: list[Any] = []
    for line in lines:
        try:
            records.append(redact(json.loads(line)))
        except json.JSONDecodeError:
            records.append({"raw": redact(line)})
    return {"data": records, "source": "target:/app/shared/service.jsonl"}


@app.get("/api/evidence/config")
def get_config_evidence() -> dict[str, Any]:
    runtime = json.loads(console.docker_read("/app/shared/runtime_config.json"))
    deployment = json.loads(console.docker_read("/app/metadata/deployment.json"))
    runbook = console.docker_read("/app/runbook/runbook.md")
    return {
        "runtime_config": redact(runtime),
        "deployment": redact(deployment),
        "runbook": redact(runbook),
    }


@app.post("/api/local/start", status_code=202)
def start_local() -> dict[str, Any]:
    return console.start_local()


@app.post("/api/local/reset", status_code=202)
def reset_local() -> dict[str, Any]:
    return console.reset_local()


@app.post("/api/local/stop")
def stop_local() -> dict[str, Any]:
    return console.stop_local()


@app.post("/api/approval", status_code=202)
def record_approval(request: ApprovalRequest) -> dict[str, Any]:
    return console.approve(request)
