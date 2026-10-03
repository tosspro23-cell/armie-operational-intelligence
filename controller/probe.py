"""Real HTTP probes used as local evidence, not faked controller results."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from . import config
from .events import EventCapture


def request_json(path: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        f"{config.TARGET_BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return {
                "path": path,
                "status": response.status,
                "body": json.loads(response.read().decode("utf-8")),
            }
    except urllib.error.HTTPError as exc:
        try:
            return {
                "path": path,
                "status": exc.code,
                "body": json.loads(exc.read().decode("utf-8")),
            }
        finally:
            exc.close()


def wait_for_health(timeout: float = 60.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            result = request_json("/health")
            if result["status"] == 200:
                return result
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise TimeoutError(f"target did not become healthy: {last_error}")


def probe_incident(capture: EventCapture, count: int = 8) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []

    def record(label: str, result: dict[str, Any]) -> None:
        item = {"label": label, **result}
        probes.append(item)
        capture.controller("target_probe", item)

    record("health", request_json("/health"))
    record("metrics_before", request_json("/metrics"))
    record("downstream_diagnostic", request_json("/diagnostics/downstream"))
    for index in range(count):
        record(
            f"checkout_{index + 1}",
            request_json(
                "/checkout",
                method="POST",
                body={"order_id": f"incident-order-{index + 1}", "amount_cents": 1099},
            ),
        )
    record("metrics_after", request_json("/metrics"))
    return probes


def write_probe_artifact(run_dir: Path, probes: list[dict[str, Any]]) -> None:
    path = run_dir / "target_probe.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for item in probes:
            handle.write(json.dumps(item, sort_keys=True) + "\n")


def snapshot_runtime(run_dir: Path) -> None:
    """Copy generated evidence out of the named Docker volume."""

    result = subprocess.run(
        ["docker", "compose", "-f", str(config.COMPOSE_FILE), "ps", "-q", "target"],
        cwd=config.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    container_id = result.stdout.strip()
    if result.returncode != 0 or not container_id:
        raise RuntimeError("could not resolve target container for evidence snapshot")
    snapshot_dir = run_dir / "runtime"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    copy_result = subprocess.run(
        ["docker", "cp", f"{container_id}:/app/shared/.", str(snapshot_dir)],
        cwd=config.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if copy_result.returncode != 0:
        raise RuntimeError(f"could not snapshot target runtime evidence: {copy_result.stderr}")
    config.RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    for source in snapshot_dir.iterdir():
        if source.is_file():
            shutil.copyfile(source, config.RUNTIME_ROOT / source.name)
