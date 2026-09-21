"""FastAPI adapter around the deterministic synthetic payment service."""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .domain import RuntimeConfig, SyntheticPaymentService


def _read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


class JsonlLogger:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def emit(self, event: str, **fields: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "service": os.environ.get("SERVICE_NAME", "synthetic-payment-api"),
            **fields,
        }
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, sort_keys=True) + "\n")


config = RuntimeConfig.from_mapping(
    _read_json(os.environ.get("RUNTIME_CONFIG_PATH", "/app/shared/runtime_config.json"))
)
deployment = _read_json(
    os.environ.get("DEPLOYMENT_METADATA_PATH", "/app/metadata/deployment.json")
)
incident_timeline = _read_json(
    os.environ.get("INCIDENT_TIMELINE_PATH", "/app/metadata/incident_timeline.json")
)
service = SyntheticPaymentService(config)
logger = JsonlLogger(os.environ.get("LOG_PATH", "/app/logs/service.jsonl"))
metrics_path = Path(os.environ.get("METRICS_PATH", "/app/shared/metrics.json"))
app = FastAPI(title="synthetic-payment-api", version=config.service_version)


class CheckoutRequest(BaseModel):
    order_id: str
    amount_cents: int


def _persist_metrics() -> None:
    metrics_path.write_text(json.dumps(service.metrics(), indent=2) + "\n", encoding="utf-8")


logger.emit(
    "service_started",
    version=config.service_version,
    mode=config.mode,
    deployment_id=deployment.get("deployment_id"),
)
logger.emit(
    "deployment_loaded",
    deployment_id=deployment.get("deployment_id"),
    deployed_at=deployment.get("deployed_at"),
    previous_version=deployment.get("previous_version"),
)
logger.emit(
    "runtime_config_loaded",
    mode=config.mode,
    checkout_timeout_ms=config.checkout_timeout_ms,
    downstream_latency_ms=config.downstream_latency_ms,
    downstream_status=config.downstream_status,
)
_persist_metrics()


@app.get("/health")
def health() -> dict[str, Any]:
    payload = service.health()
    logger.emit("health_checked", **payload)
    return payload


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    payload = service.metrics()
    logger.emit("metrics_read", **payload)
    return payload


@app.get("/diagnostics/downstream")
def downstream_diagnostics() -> dict[str, Any]:
    warning = config.downstream_latency_ms > config.dependency_warning_threshold_ms
    payload = {
        "dependency": "payment-gateway-simulator",
        "status": config.downstream_status,
        "observed_latency_ms": config.downstream_latency_ms,
        "warning": warning,
        "warning_threshold_ms": config.dependency_warning_threshold_ms,
    }
    logger.emit("downstream_diagnostic_read", **payload)
    return payload


@app.get("/diagnostics/timeline")
def incident_timeline_diagnostics() -> dict[str, Any]:
    """Return a fresh control-plane observation for the second investigation turn."""

    payload = dict(incident_timeline)
    logger.emit(
        "incident_timeline_diagnostic_read",
        source=payload.get("source"),
        timeout_budget_ms=payload.get("timeout_budget_ms"),
        pre_incident_latency_ms=payload.get("pre_incident_observation", {}).get(
            "downstream_latency_ms"
        ),
        incident_latency_ms=payload.get("incident_observation", {}).get(
            "downstream_latency_ms"
        ),
    )
    return payload


@app.post("/checkout")
def checkout(request: CheckoutRequest, raw_request: Request) -> JSONResponse:
    request_id = raw_request.headers.get("x-request-id", str(uuid.uuid4()))
    logger.emit(
        "checkout_received",
        request_id=request_id,
        order_id=request.order_id,
        amount_cents=request.amount_cents,
    )
    try:
        result = service.checkout(request.order_id, request.amount_cents)
    except ValueError as exc:
        logger.emit("checkout_rejected", request_id=request_id, reason=str(exc))
        return JSONResponse(status_code=400, content={"error": str(exc)})
    logger.emit(
        "downstream_response",
        request_id=request_id,
        status=config.downstream_status,
        latency_ms=result.downstream_latency_ms,
        warning=result.dependency_warning,
    )
    if result.status_code != 200:
        logger.emit(
            "checkout_failed",
            request_id=request_id,
            outcome=result.outcome,
            error_code=result.error_code,
        )
    else:
        logger.emit("checkout_succeeded", request_id=request_id)
    _persist_metrics()
    body = {
        "request_id": request_id,
        "outcome": result.outcome,
        "error_code": result.error_code,
        "downstream_latency_ms": result.downstream_latency_ms,
    }
    return JSONResponse(status_code=result.status_code, content=body)
