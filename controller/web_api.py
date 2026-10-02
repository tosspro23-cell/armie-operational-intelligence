"""Local-only FastAPI presentation and control API for the SRE console.

This module is a thin adapter over the existing deterministic controller. It
does not create an Agent, expose arbitrary commands, or replace the Agents API
session runner. The browser receives sanitized state and lifecycle events only.
"""

from __future__ import annotations

import asyncio
import json
import os
import queue
import subprocess
import sys
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


class LiveApprovalRequest(BaseModel):
    decision: Literal["approve", "deny"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json_file(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return records
    for line in lines:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


def _latest_agents_run() -> Path | None:
    root = config.ARTIFACTS_ROOT / "runs"
    if not root.is_dir():
        return None
    candidates = [
        path
        for path in root.iterdir()
        if path.is_dir()
        and (path / "session.json").is_file()
        and (path / "agents_api_events.jsonl").is_file()
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _event_type_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        payload = record.get("payload")
        event = payload.get("event") if isinstance(payload, dict) else None
        event_type = event.get("type") if isinstance(event, dict) else None
        if isinstance(event_type, str):
            counts[event_type] = counts.get(event_type, 0) + 1
    return dict(sorted(counts.items()))


def _stable_identifier_label(value: Any) -> Any:
    """Expose a stable UI label without returning a complete runtime ID."""

    if not isinstance(value, str):
        return value
    prefix = value.split("_", 1)[0]
    return f"{prefix}_…{value[-10:] if len(value) > 10 else '[redacted]'}"


def _public_identity(identity: dict[str, Any]) -> dict[str, Any]:
    public = dict(identity)
    for key in ("agent_id", "agents_api_session_id", "agents_api_environment_id"):
        if key in public:
            public[key] = _stable_identifier_label(public[key])
    return public


def _turn_snapshot(run_dir: Path, label: str) -> dict[str, Any]:
    final_path = run_dir / f"{label}_final.md"
    events_path = run_dir / f"{label}_events.jsonl"
    final_text = ""
    if final_path.is_file():
        try:
            final_text = redact(final_path.read_text(encoding="utf-8"))
        except OSError:
            final_text = ""
    events = _read_jsonl(events_path)
    event_types = _event_type_counts(events)
    return {
        "label": label,
        "status": "completed" if final_text else "not_available",
        "final": final_text,
        "event_count": len(events),
        "event_types": event_types,
    }


def live_run_snapshot() -> dict[str, Any]:
    """Expose only redacted, read-only evidence from the latest real API run."""

    run_dir = _latest_agents_run()
    if run_dir is None:
        return {"available": False, "message": "No real Agents API run artifacts are available."}

    identity = _read_json_file(run_dir / "runtime_identity.json")
    identity = _public_identity(redact(identity)) if isinstance(identity, dict) else {}
    controller_records = _read_jsonl(run_dir / "controller_events.jsonl")
    agent_records = _read_jsonl(run_dir / "agents_api_events.jsonl")
    controller_timeline = [
        {
            "kind": record.get("kind"),
            "captured_at": record.get("captured_at"),
        }
        for record in controller_records
        if isinstance(record.get("kind"), str)
    ]
    kinds = [record.get("kind") for record in controller_records]
    mutation_executed = any(
        kind in {"remediation_config_restored", "remediation_restart"}
        for kind in kinds
    )
    proposal_path = run_dir / "remediation_proposal_final.md"
    proposal_text = ""
    if proposal_path.is_file():
        try:
            proposal_text = redact(proposal_path.read_text(encoding="utf-8"))
        except OSError:
            proposal_text = ""

    probes = _read_jsonl(run_dir / "target_probe.jsonl")
    checkout_probes = [
        record for record in probes if str(record.get("label", "")).startswith("checkout_")
    ]
    latest_probe = probes[-1] if probes else {}
    status = "running"
    if "approval_decision" in kinds:
        status = "approved_or_denied"
    elif proposal_text:
        status = "approval_pending"

    return {
        "available": True,
        "run_id": run_dir.name,
        "updated_at": datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc).isoformat(),
        "status": status,
        "identity": identity,
        "target": {
            "health": next((record for record in probes if record.get("label") == "health"), None),
            "metrics": next((record for record in reversed(probes) if str(record.get("label", "")).startswith("metrics")), None),
            "checkout_samples": len(checkout_probes),
            "checkout_statuses": [record.get("status") for record in checkout_probes],
            "latest_checkout": redact(checkout_probes[-1]) if checkout_probes else None,
            "latest_probe": redact(latest_probe),
        },
        "session": {
            "session_id": identity.get("agents_api_session_id"),
            "environment_id": identity.get("agents_api_environment_id"),
            "connected": "environment_connected" in kinds,
            "model": identity.get("configured_model"),
        },
        "turns": [
            _turn_snapshot(run_dir, "initial_investigation"),
            _turn_snapshot(run_dir, "contradictory_evidence_reassessment"),
            _turn_snapshot(run_dir, "remediation_proposal"),
            _turn_snapshot(run_dir, "post_remediation_verification"),
        ],
        "agent_event_type_counts": _event_type_counts(agent_records),
        "controller_timeline": controller_timeline[-80:],
        "proposal": {
            "text": proposal_text,
            "mutation_executed": mutation_executed,
            "approval_recorded": "approval_decision" in kinds,
            "verification_completed": (run_dir / "post_remediation_verification_final.md").is_file(),
        },
    }


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

    def simulate_payment(self) -> dict[str, Any]:
        """Run one fixed synthetic checkout for the customer-facing demo.

        The browser cannot choose a target path, command, or arbitrary payload.
        This endpoint always exercises the experiment's checkout operation with
        a fixed local test order, then refreshes the observed metrics.
        """

        try:
            checkout = request_json(
                "/checkout",
                method="POST",
                body={"order_id": "ui-demo-order", "amount_cents": 1099},
            )
            metrics = request_json("/metrics")
        except Exception as exc:
            raise HTTPException(status_code=503, detail="synthetic checkout is unavailable") from exc

        with self.lock:
            self.state["target"]["last_checkout"] = {
                "label": "ui_simulated_checkout",
                **checkout,
            }
            self.state["target"]["metrics"] = metrics
        body = checkout.get("body", {}) if isinstance(checkout.get("body"), dict) else {}
        self.emit(
            "payment.checkout.simulated",
            {
                "status": checkout.get("status"),
                "error_code": body.get("error_code"),
                "request_id": body.get("request_id"),
                "order_id": "ui-demo-order",
            },
        )
        return {"checkout": checkout, "metrics": metrics}

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
live_resume_lock = threading.RLock()
live_resume_process: subprocess.Popen[bytes] | None = None
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


@app.get("/api/live-run")
def get_live_run() -> dict[str, Any]:
    return live_run_snapshot()


@app.post("/api/live-run/approval", status_code=202)
def approve_live_run(request: LiveApprovalRequest) -> dict[str, Any]:
    """Start the bounded same-session approval continuation from the Workbench."""

    snapshot = live_run_snapshot()
    if not snapshot.get("available") or snapshot.get("status") != "approval_pending":
        raise HTTPException(status_code=409, detail="no live run is waiting for approval")
    try:
        config.require_openai_api_key()
        config.require_executor_api_key()
        config.require_runtime_identifiers()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="controller credential readiness is unavailable") from exc

    run_id = snapshot.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise HTTPException(status_code=409, detail="live run identifier is unavailable")
    with live_resume_lock:
        global live_resume_process
        if live_resume_process is not None and live_resume_process.poll() is None:
            raise HTTPException(status_code=409, detail="live approval continuation is already running")
        command = [
            sys.executable,
            "-m",
            "controller.cli",
            "resume",
            "--run-id",
            run_id,
            "--keep-target",
            "--approve-remediation" if request.decision == "approve" else "--deny-remediation",
        ]
        log_path = config.ARTIFACTS_ROOT / "runs" / run_id / "controller_resume.log"
        with log_path.open("ab") as log_handle:
            live_resume_process = subprocess.Popen(
                command,
                cwd=config.REPO_ROOT,
                env=os.environ.copy(),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
            )
    return {"status": "accepted", "run_id": run_id, "decision": request.decision}


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


@app.post("/api/checkout/simulate")
def simulate_checkout() -> dict[str, Any]:
    return console.simulate_payment()


@app.post("/api/local/stop")
def stop_local() -> dict[str, Any]:
    return console.stop_local()


@app.post("/api/approval", status_code=202)
def record_approval(request: ApprovalRequest) -> dict[str, Any]:
    return console.approve(request)
