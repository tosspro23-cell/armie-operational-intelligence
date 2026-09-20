# ARMIE Architecture Spike #001 — OpenAI Agents API local SRE runtime

Status: implementation is present, deterministic tests pass, and the live
acceptance run is blocked at the local Docker/credential boundary. No real
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

Not reached. A real session was not created because the required
`OPENAI_API_KEY` was absent and Docker could not start the isolated executor
environment. No agent-generated tool call, shell action, or model output was
fabricated.

## 6. Hypotheses Generated

The experiment presents two plausible explanations: a recent application or
deployment regression, and downstream latency/pressure. Record the agent's
actual hypotheses and confidence here after the live run; do not substitute
controller expectations.

## 7. Evidence Gathered

The deterministic tests prove the domain-level fault and safe behavior. The
Docker target image built successfully, but the target service did not start,
so no live HTTP or structured-log evidence is claimed.

## 8. Hypothesis Revision Test

The controller obtains a fresh read-only downstream diagnostic and sends it to
the same session. Record whether the agent revises its timeline, leading
hypothesis, competing hypothesis, confidence, and next step.

## 9. Human Approval Behavior

The controller prints `Approve proposed remediation? [y/N]`. Empty input,
`N`, and non-interactive execution are denied. No mutation is permitted before
an explicit approval event.

## 10. Remediation and Verification

Not reached. Remediation was not executed and post-remediation verification was
not applicable. The approval gate remains implemented with a default denial.

## 11. Session Persistence Observations

Not reached. There is no session ID to compare.

## 12. Managed Harness Responsibilities

The Agents API manages the session conversation, turns, model execution, tool
and shell interaction through the connected executor, and event stream.

## 13. Application Responsibilities

This repository provisions the target and evidence, creates the session,
connects the self-hosted executor, captures events, introduces the
contradictory observation, enforces the approval gate, and controls the one
bounded remediation.

## 14. Self-Hosted Environment Observations

The target Docker image built successfully. Docker Desktop then left the
target container in `Created` state. A minimal `busybox:latest` `echo hello`
container and a detached `busybox:latest sleep 5` container also remained in
`Created`, showing that the boundary was not specific to the target image or
the original host bind mounts. `docker start`, `docker logs`, and `docker
inspect` timed out. The executor image was therefore not started.

## 15. Event/Observability Quality

The capture implementation is present, but no live Agents API JSONL stream was
produced. The deterministic controller tests verified artifact persistence and
secret-shaped value redaction.

## 16. Failures and Limitations

The official self-hosted guidance recommends a separate restricted environment
key for `CODEX_API_KEY`. The user-specified credential boundary permits only
`OPENAI_API_KEY`, so the controller is designed to pass that value to the
isolated executor at runtime and report the least-privilege limitation if the
run reaches that point. No credential was persisted.

Observed blockers on 2026-09-20:

- `OPENAI_API_KEY` was missing in the invoking environment, so the controller
  correctly refused to begin the real API run.
- Docker Desktop 29.8.0 on `aarch64` could build images and pull layers but did
  not start even a minimal container; created containers remained `Created`
  and bounded start/log/inspect attempts timed out.
- GitHub CLI authentication for `tosspro23-cell` was present but the token was
  invalid, so no GitHub repository was created in this run.

## 17. Files Changed

All experiment files are under the isolated repository root, with runtime code
under `controller/`, `target_service/`, `sre_environment/`, `fixtures/`, and
`tests/`. Generated runtime outputs are under ignored `artifacts/` paths.

## 18. Exact Reproduction Commands

```bash
cd /Users/ting/Documents/New\ project/armie-operational-intelligence
python3 -m unittest discover -s tests -v
python3 -m controller.cli prepare
docker compose up -d target
python3 -m controller.cli probe
export OPENAI_API_KEY='...'
python3 -m controller.cli run
```

The last command must be run by a human who understands the approval boundary,
after Docker can start containers and `OPENAI_API_KEY` is set.

## 19. Architecture Observations

Factual observation at this boundary: the code path and deterministic tests are
available, but the completion gate is not satisfied. A follow-up run must
revalidate local Docker, export `OPENAI_API_KEY`, create a real session, and
capture the full same-session trace before this report can be marked complete.
This spike does not decide the final ARMIE architecture or recommend
production adoption.
