"""CLI for deterministic local proof and the real Agents API acceptance run."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable
from typing import Any

from . import config
from .api import AgentApiClient
from .events import EventCapture, redact, runtime_identity
from .probe import (
    probe_incident,
    request_json,
    snapshot_runtime,
    wait_for_health,
    write_probe_artifact,
)
from .remediation import ApprovalRequired, apply_known_safe_remediation, approval_from_text
from .runner import AttachedExecutor, SessionRunner


def new_run() -> tuple[Path, EventCapture]:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = config.ARTIFACTS_ROOT / "runs" / run_id
    return run_dir, EventCapture(run_dir)


def prepare_runtime() -> None:
    config.RUNTIME_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(
        config.FIXTURES_ROOT / "runtime_config_fault.json",
        config.RUNTIME_ROOT / "runtime_config.json",
    )
    for name in ("service.jsonl", "metrics.json"):
        path = config.RUNTIME_ROOT / name
        if path.exists():
            path.write_text("" if name.endswith(".jsonl") else "{}\n", encoding="utf-8")
    print(f"prepared {(config.RUNTIME_ROOT / 'runtime_config.json').relative_to(config.REPO_ROOT)}")


def compose_up(force_recreate: bool = False) -> None:
    command = [
        "docker",
        "compose",
        "-f",
        str(config.COMPOSE_FILE),
        "up",
        "-d",
    ]
    if os.environ.get("ARMIE_REUSE_LOCAL_IMAGES") == "1":
        command.append("--no-build")
    else:
        command.append("--build")
    if force_recreate:
        command.append("--force-recreate")
    command.append("target")
    try:
        child_env = dict(os.environ)
        child_env["RESET_RUNTIME_CONFIG"] = "1"
        result = subprocess.run(
            command,
            cwd=config.REPO_ROOT,
            env=child_env,
            check=False,
            timeout=90,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Docker Compose timed out before the target container started") from exc
    if result.returncode != 0:
        raise RuntimeError("docker compose could not start target")


def compose_stop() -> None:
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(config.COMPOSE_FILE), "stop", "target"],
            cwd=config.REPO_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        # Cleanup must not hide the actual acceptance-run failure.
        return


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def extract_final_assistant_text(items: Any) -> str | None:
    """Extract the latest completed assistant message from session items.

    Streaming deltas and command/tool outputs are deliberately excluded. The
    API's persisted session items are the source of truth for the final turn
    answer after a completed turn.
    """

    if not isinstance(items, dict) or not isinstance(items.get("data"), list):
        return None
    candidates: list[str] = []
    for item in items["data"]:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", "")).lower()
        is_assistant_message = item.get("role") == "assistant" or item_type in {
            "agent_session_assistant_message",
            "assistant_message",
        }
        if item_type == "message" and item.get("role") != "user":
            is_assistant_message = True
        if not is_assistant_message:
            continue
        if item.get("status") in {"in_progress", "incomplete"}:
            continue
        text = _content_text(item.get("content"))
        if not text and isinstance(item.get("text"), str):
            text = item["text"].strip()
        if text:
            candidates.append(text)
    return candidates[-1] if candidates else None


def write_turn_artifacts(
    run_dir: Path,
    capture: EventCapture,
    label: str,
    turn: dict[str, Any],
) -> None:
    """Persist one turn's event slice and API item-derived final text."""

    events = turn.get("events", [])
    with (run_dir / f"{label}_events.jsonl").open("w", encoding="utf-8") as handle:
        for raw_name, payload in events:
            record = {"raw_event_name": raw_name, "event": redact(payload)}
            handle.write(json.dumps(record, sort_keys=True) + "\n")
    final_text = extract_final_assistant_text(turn.get("items"))
    if final_text is None:
        final_text = "No completed assistant message item was captured."
    capture.write_text(f"{label}_final.md", final_text + "\n")


def validate_executor_boundary(capture: EventCapture) -> None:
    """Exercise the executor image without starting codex exec-server."""

    command = [
        "docker",
        "compose",
        "-f",
        str(config.COMPOSE_FILE),
        "run",
        "--rm",
        "--no-deps",
        "--entrypoint",
        "sh",
        "sre_environment",
        "-c",
        (
            "set -eu; "
            "curl -fsS http://target:8080/health >/tmp/target-health.json; "
            "test -r /workspace/artifacts/runtime/runtime_config.json; "
            "if touch /workspace/artifacts/runtime/controller-must-not-write; then "
            "exit 41; else exit 0; fi"
        ),
    ]
    result = subprocess.run(
        command,
        cwd=config.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
    )
    capture.controller(
        "executor_boundary_check",
        {
            "returncode": result.returncode,
            "target_reachable": result.returncode == 0,
            "evidence_readable": result.returncode == 0,
            "evidence_write_denied": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
        },
    )
    if result.returncode != 0:
        raise RuntimeError("isolated executor boundary validation failed")


def run_real(
    approve_remediation: bool,
    keep_target: bool,
    approval_provider: Callable[[Path], bool] | None = None,
    prepared_run: Path | None = None,
) -> int:
    """Run the real acceptance flow.

    ``approval_provider`` is used by the browser controller. It pauses after
    the Agent has produced a proposal and resumes only after the Controller
    receives an explicit human decision. The default CLI path remains the
    interactive terminal prompt.
    """

    if prepared_run is None:
        run_dir, _ = new_run()
    else:
        run_dir = prepared_run
    capture = EventCapture(run_dir)
    capture.controller("run_started", {"run_dir": str(run_dir.relative_to(config.REPO_ROOT))})
    runner: SessionRunner | None = None
    try:
        prepare_runtime()
        compose_up()
        health = wait_for_health()
        capture.controller("target_started", health)
        validate_executor_boundary(capture)
        probes = probe_incident(capture)
        write_probe_artifact(run_dir, probes)
        snapshot_runtime(run_dir)

        credential_state = config.credential_presence()
        capture.controller("credential_readiness", credential_state)
        print(
            "credential readiness: "
            + ", ".join(f"{name}={state}" for name, state in credential_state.items())
        )
        if "missing" in credential_state.values():
            raise RuntimeError("credential readiness boundary: one or more required keys are missing")
        agent_id, project_id = config.require_runtime_identifiers()
        key = config.require_openai_api_key()
        config.require_executor_api_key()
        client = AgentApiClient(key, capture, project_id)
        session = client.create_session(config.session_payload(agent_id, project_id))
        session_id = str(session.get("id", ""))
        if not session_id:
            raise RuntimeError("Agents API response did not include a session ID")
        capture.write_json("session.json", session)
        environment = session.get("environment", {})
        environment_id = environment.get("id") if isinstance(environment, dict) else None
        capture.write_json(
            "runtime_identity.json",
            runtime_identity(session_id, agent_id, environment_id),
        )
        capture.controller(
            "session_created",
            {
                "session_id": session_id,
                "agent_id": session.get("agent", {}).get("id", agent_id),
                "model": session.get("agent", {}).get("model", config.MODEL),
                "environment_type": session.get("environment", {}).get("type"),
            },
        )

        runner = SessionRunner(client, capture, session)
        runner.start_executor()
        turn = runner.run_turn(
            "initial_investigation", config.INITIAL_USER_MESSAGE, wait_for_connection=True
        )
        write_turn_artifacts(run_dir, capture, "initial_investigation", turn)

        contradiction = request_json("/diagnostics/timeline")
        capture.controller("contradictory_observation", contradiction)
        contradiction_message = (
            "A fresh read-only control-plane timeline diagnostic has arrived. It "
            f"reports that the {contradiction['body'].get('timeout_budget_ms')} ms "
            "checkout timeout budget was first observed before the deployment, "
            f"checkout was {contradiction['body'].get('pre_incident_observation', {}).get('checkout_status')} "
            f"when dependency latency was {contradiction['body'].get('pre_incident_observation', {}).get('downstream_latency_ms')} ms, "
            "and checkout was "
            f"{contradiction['body'].get('incident_observation', {}).get('checkout_status')} "
            f"when latency rose to {contradiction['body'].get('incident_observation', {}).get('downstream_latency_ms')} ms. "
            "Reassess the timeline, your leading and competing hypotheses, "
            "confidence, and safest next step. Do not make changes. Cite the "
            "evidence you used."
        )
        turn = runner.run_turn("contradictory_evidence_reassessment", contradiction_message)
        write_turn_artifacts(run_dir, capture, "contradictory_evidence_reassessment", turn)

        proposal_message = (
            "Based on the revised assessment, produce an evidence-backed proposed "
            "remediation. Keep it bounded to this synthetic experiment. State the "
            "exact action, risks, verification plan, and rollback plan. Do not execute "
            "anything and wait for explicit human approval."
        )
        turn = runner.run_turn("remediation_proposal", proposal_message)
        write_turn_artifacts(run_dir, capture, "remediation_proposal", turn)

        approved = approve_remediation
        approval_source = "explicit_flag_or_human_prompt"
        if not approve_remediation:
            if approval_provider is not None:
                capture.controller(
                    "approval_pending",
                    {"source": "workbench", "default": "deny"},
                )
                approved = approval_provider(run_dir)
                approval_source = "workbench"
            elif sys.stdin.isatty():
                approved = approval_from_text(input("Approve proposed remediation? [y/N] "))
            else:
                print("Approve proposed remediation? [y/N] (non-interactive default: N)")
                approved = False
        capture.controller(
            "approval_decision",
            {"approved": approved, "source": approval_source},
        )
        capture.write_json(
            "approval_record.json",
            {"approved": approved, "source": approval_source},
        )
        if not approved:
            try:
                apply_known_safe_remediation(capture, approved=False)
            except ApprovalRequired as exc:
                capture.controller("remediation_blocked", {"reason": str(exc)})
            print(f"run complete at approval boundary: {run_dir}")
            return 0

        apply_known_safe_remediation(capture, approved=True)
        wait_for_health()
        recovery_probes = probe_incident(capture, count=1)
        write_probe_artifact(run_dir, probes + recovery_probes)
        snapshot_runtime(run_dir)
        turn = runner.run_turn(
            "post_remediation_verification",
            "The approved bounded remediation has now been applied by the controller. "
            "Inspect the actual health, checkout response, metrics, and new logs. "
            "Verify recovery independently, report remaining uncertainty, and do not "
            "assume success from the controller's statement.",
        )
        write_turn_artifacts(run_dir, capture, "post_remediation_verification", turn)
        print(f"run complete with verification at approval boundary: {run_dir}")
        return 0
    except Exception as exc:
        capture.controller("run_failed", {"error_type": type(exc).__name__, "error": str(exc)})
        print(f"real acceptance run stopped at actual boundary: {exc}", file=sys.stderr)
        print(f"partial artifacts: {run_dir}", file=sys.stderr)
        return 2
    finally:
        if runner is not None:
            runner.stop()
        if not keep_target:
            compose_stop()


def _running_executor_id() -> str:
    result = subprocess.run(
        ["docker", "compose", "-f", str(config.COMPOSE_FILE), "ps", "-q", "sre_environment"],
        cwd=config.REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    container_id = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if not container_id:
        # `docker compose run` creates a one-off container that is visible to
        # Docker's label filter but is intentionally omitted by `compose ps -q`.
        result = subprocess.run(
            [
                "docker",
                "ps",
                "--filter",
                "label=com.docker.compose.service=sre_environment",
                "--filter",
                "status=running",
                "--format",
                "{{.ID}}",
            ],
            cwd=config.REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        container_id = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    if result.returncode != 0 or not container_id:
        raise RuntimeError("no running self-hosted executor is available for session resume")
    return container_id


def _stored_probes(run_dir: Path) -> list[dict[str, Any]]:
    path = run_dir / "target_probe.jsonl"
    if not path.is_file():
        return []
    probes: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            probes.append(value)
    return probes


def run_resume(
    run_id: str,
    approve_remediation: bool,
    keep_target: bool,
    deny_remediation: bool = False,
) -> int:
    """Resume only the approval and verification stages of an existing run."""

    run_dir = config.ARTIFACTS_ROOT / "runs" / run_id
    session_path = run_dir / "session.json"
    proposal_path = run_dir / "remediation_proposal_final.md"
    approval_path = run_dir / "approval_record.json"
    if not session_path.is_file() or not proposal_path.is_file():
        raise RuntimeError("resume requires an existing run with a captured proposal")
    if approval_path.exists():
        raise RuntimeError("approval has already been recorded for this run")
    if approve_remediation and deny_remediation:
        raise RuntimeError("resume approval decision cannot be both approve and deny")

    session = json.loads(session_path.read_text(encoding="utf-8"))
    session_id = str(session.get("id", ""))
    environment = session.get("environment") or {}
    environment_id = environment.get("id") if isinstance(environment, dict) else None
    agent = session.get("agent") or {}
    if not session_id or not isinstance(environment_id, str) or not environment_id:
        raise RuntimeError("stored session does not contain a resumable environment")

    capture = EventCapture(run_dir)
    runner: SessionRunner | None = None
    try:
        config.require_openai_api_key()
        config.require_executor_api_key()
        _, project_id = config.require_runtime_identifiers()
        client = AgentApiClient(config.require_openai_api_key(), capture, project_id)
        current = client.retrieve_session(session_id)
        current_id = str(current.get("id", ""))
        if current_id != session_id:
            raise RuntimeError("retrieved session ID does not match the stored run")
        capture.controller(
            "session_reconnected",
            {
                "session_id": session_id,
                "environment_id": environment_id,
                "session_status": current.get("status"),
                "agent_id": agent.get("id"),
            },
        )
        capture.write_json(
            "resume_runtime_identity.json",
            runtime_identity(session_id, agent.get("id"), environment_id),
        )
        executor_id = _running_executor_id()
        attached = AttachedExecutor(executor_id)
        attached.ensure_alive()
        capture.controller(
            "executor_reconnected",
            {"container_id": executor_id, "environment_id": environment_id},
        )
        runner = SessionRunner(client, capture, session, executor=attached)

        approved = approve_remediation
        if deny_remediation:
            approved = False
        elif not approve_remediation:
            if sys.stdin.isatty():
                approved = approval_from_text(input("Approve proposed remediation? [y/N] "))
            else:
                print("Approve proposed remediation? [y/N] (non-interactive default: N)")
        capture.controller(
            "approval_decision",
            {"approved": approved, "source": "explicit_flag_or_human_prompt"},
        )
        capture.write_json(
            "approval_record.json",
            {
                "approved": approved,
                "source": "explicit_flag_or_human_prompt",
                "session_id": session_id,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        if not approved:
            try:
                apply_known_safe_remediation(capture, approved=False)
            except ApprovalRequired as exc:
                capture.controller("remediation_blocked", {"reason": str(exc)})
            print(f"run resumed and denied at approval boundary: {run_dir}")
            return 0

        apply_known_safe_remediation(capture, approved=True)
        health = wait_for_health()
        capture.controller("target_started", health)
        recovery_probes = probe_incident(capture, count=1)
        write_probe_artifact(run_dir, _stored_probes(run_dir) + recovery_probes)
        snapshot_runtime(run_dir)
        turn = runner.run_turn(
            "post_remediation_verification",
            "The approved bounded remediation has now been applied by the controller. "
            "Inspect the actual health, checkout response, metrics, and new logs. "
            "Verify recovery independently, report remaining uncertainty, and do not "
            "assume success from the controller's statement.",
        )
        write_turn_artifacts(run_dir, capture, "post_remediation_verification", turn)
        print(f"run resumed with verification: {run_dir}")
        return 0
    finally:
        if runner is not None:
            runner.stop()
        if not keep_target:
            compose_stop()


def run_probe() -> int:
    prepare_runtime()
    compose_up()
    try:
        run_dir, capture = new_run()
        wait_for_health()
        validate_executor_boundary(capture)
        probes = probe_incident(capture)
        write_probe_artifact(run_dir, probes)
        snapshot_runtime(run_dir)
        print(f"local incident evidence: {run_dir}")
        return 0
    finally:
        compose_stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("prepare")
    subparsers.add_parser("probe")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--approve-remediation", action="store_true")
    run_parser.add_argument("--keep-target", action="store_true")
    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--run-id", required=True)
    decision = resume_parser.add_mutually_exclusive_group()
    decision.add_argument("--approve-remediation", action="store_true")
    decision.add_argument("--deny-remediation", action="store_true")
    resume_parser.add_argument("--keep-target", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare_runtime()
        return 0
    if args.command == "probe":
        return run_probe()
    if args.command == "resume":
        return run_resume(
            args.run_id,
            args.approve_remediation,
            args.keep_target,
            args.deny_remediation,
        )
    return run_real(args.approve_remediation, args.keep_target)


if __name__ == "__main__":
    raise SystemExit(main())
