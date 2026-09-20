"""CLI for deterministic local proof and the real Agents API acceptance run."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .api import AgentApiClient
from .events import EventCapture, runtime_identity
from .probe import (
    probe_incident,
    request_json,
    snapshot_runtime,
    wait_for_health,
    write_probe_artifact,
)
from .remediation import ApprovalRequired, apply_known_safe_remediation, approval_from_text
from .runner import SessionRunner


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


def compose_up() -> None:
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(config.COMPOSE_FILE), "down", "-v", "--remove-orphans"],
            cwd=config.REPO_ROOT,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        result = subprocess.run(
            ["docker", "compose", "-f", str(config.COMPOSE_FILE), "up", "-d", "--build", "target"],
            cwd=config.REPO_ROOT,
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


def compact_agent_text(payload: Any) -> list[str]:
    found: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in {"text", "output_text", "delta"} and isinstance(value, str):
                if value.strip():
                    found.append(value.strip())
            else:
                found.extend(compact_agent_text(value))
    elif isinstance(payload, list):
        for item in payload:
            found.extend(compact_agent_text(item))
    return found


def append_turn_text(run_dir: Path, label: str, capture_path: Path) -> None:
    lines: list[str] = [f"## {label}", ""]
    try:
        for raw in capture_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(raw)
            for text in compact_agent_text(record.get("payload")):
                lines.append(text)
    except FileNotFoundError:
        lines.append("No streamed text was captured.")
    lines.append("")
    with (run_dir / "agent_turns.md").open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines))


def run_real(approve_remediation: bool, keep_target: bool) -> int:
    key = config.require_openai_api_key()
    run_dir, capture = new_run()
    capture.controller("run_started", {"run_dir": str(run_dir.relative_to(config.REPO_ROOT))})
    runner: SessionRunner | None = None
    try:
        prepare_runtime()
        compose_up()
        health = wait_for_health()
        capture.controller("target_started", health)
        probes = probe_incident(capture)
        write_probe_artifact(run_dir, probes)
        snapshot_runtime(run_dir)

        client = AgentApiClient(key, capture)
        session = client.create_session(config.session_payload())
        session_id = str(session.get("id", ""))
        if not session_id:
            raise RuntimeError("Agents API response did not include a session ID")
        capture.write_json("session.json", session)
        capture.write_json("runtime_identity.json", runtime_identity(session_id))
        capture.controller(
            "session_created",
            {
                "session_id": session_id,
                "agent_id": session.get("agent", {}).get("id", config.AGENT_ID),
                "model": session.get("agent", {}).get("model", config.MODEL),
                "environment_type": session.get("environment", {}).get("type"),
            },
        )

        runner = SessionRunner(client, capture, session)
        runner.start_executor()
        runner.run_turn("initial_investigation", config.INITIAL_USER_MESSAGE, wait_for_connection=True)
        append_turn_text(run_dir, "Initial investigation", capture.agent_path)

        contradiction = request_json("/diagnostics/downstream")
        capture.controller("contradictory_observation", contradiction)
        contradiction_message = (
            "A fresh read-only diagnostic has arrived. It reports the downstream "
            f"dependency status as {contradiction['body'].get('status')!r}, observed "
            f"latency {contradiction['body'].get('observed_latency_ms')} ms, and "
            f"warning={contradiction['body'].get('warning')}. Reassess the timeline, "
            "your leading and competing hypotheses, confidence, and safest next step. "
            "Do not make changes. Cite the evidence you used."
        )
        runner.run_turn("contradictory_evidence_reassessment", contradiction_message)
        append_turn_text(run_dir, "Contradictory evidence reassessment", capture.agent_path)

        proposal_message = (
            "Based on the revised assessment, produce an evidence-backed proposed "
            "remediation. Keep it bounded to this synthetic experiment. State the "
            "exact action, risks, verification plan, and rollback plan. Do not execute "
            "anything and wait for explicit human approval."
        )
        runner.run_turn("remediation_proposal", proposal_message)
        append_turn_text(run_dir, "Remediation proposal", capture.agent_path)

        approved = approve_remediation
        if not approve_remediation:
            if sys.stdin.isatty():
                approved = approval_from_text(input("Approve proposed remediation? [y/N] "))
            else:
                print("Approve proposed remediation? [y/N] (non-interactive default: N)")
                approved = False
        capture.controller(
            "approval_decision",
            {"approved": approved, "source": "explicit_flag_or_human_prompt"},
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
        runner.run_turn(
            "post_remediation_verification",
            "The approved bounded remediation has now been applied by the controller. "
            "Inspect the actual health, checkout response, metrics, and new logs. "
            "Verify recovery independently, report remaining uncertainty, and do not "
            "assume success from the controller's statement.",
        )
        append_turn_text(run_dir, "Post-remediation verification", capture.agent_path)
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


def run_probe() -> int:
    prepare_runtime()
    compose_up()
    try:
        run_dir, capture = new_run()
        wait_for_health()
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
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare_runtime()
        return 0
    if args.command == "probe":
        return run_probe()
    return run_real(args.approve_remediation, args.keep_target)


if __name__ == "__main__":
    raise SystemExit(main())
