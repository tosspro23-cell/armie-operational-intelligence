# ARMIE Architecture Spike #001 — OpenAI Agents API local SRE runtime

Status: implementation audit and deterministic validation are complete on
`spike/openai-agents-sre-live-validation`. The live acceptance run remains
blocked before session creation because Docker cannot start a minimal
container and both required credentials are absent from this shell. No real
Agents API session or live agent result is claimed.

## 1. Experiment Objective

Evaluate a real OpenAI Managed Agents API session, created from the saved SRE
agent definition, investigating one deterministic local SRE incident through a
self-hosted Docker execution environment.

## 2. Implemented Runtime Topology

```text
controller (local Python)
  ├─ Agents API session: saved agent + session overrides
  ├─ event capture: artifacts/runs/<run-id>/*.jsonl
  └─ human approval gate
       │
       ├─ Docker: sre_environment + codex exec-server (no Docker socket)
       │       └─ read-only evidence mounts + Docker network access
       └─ Docker: synthetic-payment-api
               └─ structured logs, metrics, config, deployment metadata, runbook
```

The self-hosted executor follows the official `codex exec-server` mechanism.
The controller is not part of the runtime agent architecture being evaluated.
The host application key and restricted executor key are separate. The
executor receives only the executor key as `CODEX_API_KEY`; the application
key is removed from its child environment.

## 3. Synthetic Incident Design

The target is `synthetic-payment-api`, a small FastAPI service exposing
`GET /health`, `GET /metrics`, `GET /diagnostics/downstream`, and `POST
/checkout`. The service emits structured JSONL logs and persists counters.

The incident has a deployment/configuration change followed by checkout errors
and a downstream latency warning. Health remains green to make liveness an
insufficient signal.

## 4. Fault Ground Truth

This section is experiment-side ground truth, not part of the initial agent
message. The fault fixture sets `checkout_timeout_ms=120` while the deterministic
simulated dependency responds in 168 ms and remains available. The known-safe
fixture restores a 300 ms timeout. The agent must reach this conclusion from
mounted runtime evidence and real HTTP/log interaction.

## 5. Agent Investigation Trace

Not reached. A real session was not created because Docker could not start the
local target or the executor, and the credential readiness gate reported both
required variables missing. No agent-generated tool call, shell action, or
model output was fabricated.

## 6. Hypotheses Generated

The experiment presents two plausible explanations: a recent application or
deployment regression, and downstream latency/pressure. Record the agent's
actual hypotheses and confidence here after the live run; do not substitute
controller expectations.

## 7. Evidence Gathered

The deterministic tests prove the domain-level fault and safe behavior. On the
validation checkout, the target image built successfully, but its container
remained `Created`; therefore no live HTTP, structured-log, target health, or
executor-boundary evidence is claimed. The local HTTP acceptance gate was not
entered.

## 8. Hypothesis Revision Test

The controller obtains a fresh read-only downstream diagnostic and sends it to
the same session. Record whether the agent revises its timeline, leading
hypothesis, competing hypothesis, confidence, and next step.

## 9. Human Approval Behavior

The controller prints `Approve proposed remediation? [y/N]`. Empty input,
`N`, and non-interactive execution are denied. No mutation is permitted before
an explicit approval event. The deterministic test also confirms the
remediation subprocess is not reached when approval is false.

## 10. Remediation and Verification

Not reached. Remediation was not executed and post-remediation verification was
not applicable. The approval gate remains implemented with a default denial.

## 11. Session Persistence Observations

Not reached. There is no session ID to compare. The runner binds every
follow-up to the session ID returned by the one session creation response and
records retrieved session items after each turn.

## 12. Managed Harness Responsibilities

The Agents API manages the session conversation, turns, model execution, tool
and shell interaction through the connected executor, and event stream. The
official self-hosted environment mechanism supplies the remote URL and
environment ID used by `codex exec-server`.

## 13. Application Responsibilities

This repository provisions the target and evidence, creates the session,
connects the self-hosted executor, captures events, introduces the
contradictory observation, enforces the approval gate, and controls the one
bounded remediation. It also validates that the executor can reach the target,
read evidence, and cannot write the read-only evidence volume.

## 14. Self-Hosted Environment Observations

The target Docker image built successfully in the validation checkout. Docker
Desktop reported client/server `29.8.0`, context `desktop-linux`, Docker
Desktop `aarch64`, and `overlayfs`; however, the target remained `Created` after
a bounded `docker compose up` attempt. The required disposable
`docker run --rm busybox:latest echo docker-ok` also produced no output and
left a `Created` container until that exact disposable test container was
removed. The executor image was not started. This is a Docker runtime blocker,
not evidence of a target application failure.

## 15. Event/Observability Quality

The capture implementation now records redacted controller events, streamed
Agents API events, per-turn event slices, retrieved session items, terminal
turn outcome, approval, remediation, and verification records. The
deterministic tests verified artifact persistence, field-aware redaction,
credential separation, approval denial, and saved-agent payload construction.
No live Agents API JSONL stream was produced in this run.

## 16. Failures and Limitations

The implementation audit found that the prior controller incorrectly reused
`OPENAI_API_KEY` as the executor credential. That is corrected: the host
controller requires `OPENAI_API_KEY`, the executor requires a separate
`OPENAI_EXECUTOR_API_KEY`, and only the latter is mapped to `CODEX_API_KEY`.
The saved agent and project identifiers are now supplied as local runtime
identifiers rather than committed source values. No credential was persisted.

Observed blockers on 2026-09-20:

- `OPENAI_API_KEY` and `OPENAI_EXECUTOR_API_KEY` were both missing in the
  invoking environment. No session request was attempted.
- Docker Desktop 29.8.0 on `aarch64` could build images and pull layers but did
  not start even a minimal container; created containers remained `Created`.
- The host `Documents` worktree also became content-read-inaccessible to shell
  commands during this run. The implementation branch was prepared in a
  disposable `/tmp` clone from the exact `develop` commit to avoid overwriting
  the user worktree. The original worktree must be rechecked after local file
  access is restored.

## 17. Files Changed

The relevant implementation changes are under `.gitignore`, `README.md`,
`.env.example`, `artifacts/README.md`, `controller/`, `docker-compose.yml`,
`target_service/entrypoint.sh`, and `tests/`. Generated runtime outputs remain
under ignored `artifacts/` paths. `AUDIT_FINDINGS.md` records the pre-fix audit
in the original local worktree and must be reconciled before relying on that
worktree's branch state.

## 18. Exact Reproduction Commands

```bash
cd /Users/ting/Documents/New\ project/armie-operational-intelligence
python3 -m unittest discover -s tests -v
python3 -m compileall -q controller target_service tests
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
docker context show
docker info --format 'server={{.ServerVersion}} os={{.OperatingSystem}} arch={{.Architecture}} running={{.ContainersRunning}} stopped={{.ContainersStopped}} images={{.Images}} driver={{.Driver}}'
docker run --rm busybox:latest echo docker-ok
python3 -m controller.cli prepare
docker compose up -d target
python3 -m controller.cli probe
export OPENAI_API_KEY='...'
export OPENAI_EXECUTOR_API_KEY='...'
export ARMIE_SRE_AGENT_ID='...'
export OPENAI_PROJECT_ID='...'
python3 -m controller.cli run
```

The last command must be run by a human who understands the approval boundary,
after Docker can start containers, both credential variables are set, and the
non-secret runtime identifiers are set. The values must never be pasted into
the Codex conversation.

## 19. Architecture Observations

Factual observation at this boundary: the code path and deterministic tests are
available, but the completion gate is not satisfied. A follow-up run must
restore Docker, set both credentials and runtime identifiers locally, revalidate
the synthetic incident, create a real session, and capture the full same-session
trace before this report can be marked complete. This spike does not decide the
final ARMIE architecture or recommend production adoption.
