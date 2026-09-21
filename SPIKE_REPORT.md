# ARMIE Architecture Spike #001 — OpenAI Agents API local SRE runtime

Status: Docker, the local synthetic incident, and the controlled approved
remediation lifecycle are now live-demonstrated on
`spike/openai-agents-sre-live-validation`. The independent review fixes are
implemented and locally tested. The real Agents API run remains blocked before
session creation because both required credentials are absent from this shell.
No real Agents API session or live agent result is claimed.

This branch also adds a local-only Vite/React console over the existing FastAPI
controller. It has been built and opened against a real Docker target; it shows
the fault, evidence, controller SSE events, and approval boundary. It does not
create or simulate an Agent API session.

## 1. Experiment Objective

Evaluate a real OpenAI Managed Agents API session, created from the saved SRE
agent definition, investigating one deterministic local SRE incident through a
self-hosted Docker execution environment.

## 2. Implemented Runtime Topology

The first UI slice is:

```text
React/Vite browser :5173
        │ local HTTP control + SSE
        ▼
FastAPI controller :8787
        ├─ real HTTP probes against synthetic-payment-api :18080
        ├─ read-only evidence readers and controller events
        └─ explicit allowlisted approval gate
```

The later live mode will add the Agents API event stream behind this same
controller boundary.

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
`GET /health`, `GET /metrics`, `GET /diagnostics/downstream`,
`GET /diagnostics/timeline`, and `POST /checkout`. The service emits
structured JSONL logs and persists counters.

The incident has a deployment/configuration change followed by checkout errors
and a downstream latency warning. Health remains green to make liveness an
insufficient signal. A separate read-only `/diagnostics/timeline` endpoint is
introduced only after the first agent turn; it records that the tight timeout
budget predates the deployment and that checkout was healthy at 118 ms before
the dependency rose to 168 ms. This gives the second turn genuinely new
evidence that challenges a deployment-only explanation.

## 4. Fault Ground Truth

This section is experiment-side ground truth, not part of the initial agent
message. The fault fixture sets `checkout_timeout_ms=120` while the deterministic
simulated dependency responds in 168 ms and remains available. The timeline
fixture records that the same budget was observed before the incident and that
118 ms had previously produced successful checkout responses. The known-safe
fixture restores a 300 ms timeout. The agent must reach its conclusion from
mounted runtime evidence and real HTTP/log interaction; these facts are not
included in the initial user message.

## 5. Agent Investigation Trace

Not reached. A real session was not created because the credential readiness
gate reported both required variables missing. No agent-generated tool call,
shell action, or model output was fabricated.

## 6. Hypotheses Generated

The experiment presents two plausible explanations: a recent application or
deployment regression, and downstream latency/pressure. Record the agent's
actual hypotheses and confidence here after the live run; do not substitute
controller expectations.

## 7. Evidence Gathered

The live target returned health 200 and eight real checkout responses with
status 504. The downstream diagnostic reported status `ok`, latency 168 ms,
and a warning threshold of 150 ms. Metrics recorded eight attempts and eight
timeouts. Structured JSONL logs, deployment metadata, runtime configuration,
and the runbook were read from the running container. The executor boundary
check reached the target, read the evidence volume, and was denied write access
by the read-only mount. A target force-recreate with the fault fixture produced
the same timeout again.

## 8. Hypothesis Revision Test

The controller obtains a fresh read-only timeline diagnostic from the running
target and sends it to the same session. The new observation contrasts
successful checkout at 118 ms before the incident with 504 responses at 168 ms,
while showing that the 120 ms budget predates the deployment. Record whether
the agent revises its timeline, leading hypothesis, competing hypotheses,
confidence, and next step after the live run.

## 9. Human Approval Behavior

The controller prints `Approve proposed remediation? [y/N]`. Empty input,
`N`, and non-interactive execution are denied. No mutation is permitted before
an explicit approval event. The deterministic test also confirms the
remediation subprocess is not reached when approval is false.

## 10. Remediation and Verification

The approved remediation path is now covered by a real Docker integration test:
the fault returns 504, the controlled remediation is explicitly approved, the
target is recreated with `RESET_RUNTIME_CONFIG=0`, and checkout then returns
200. This confirms the safe config is not overwritten on restart. The live
Agents API run has not reached its approval gate, so no live human approval or
same-session post-remediation verification is claimed yet.

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

The Docker runtime recovered during this validation: the required disposable
command printed `docker-ok`. The target and executor images built, the target
ran healthy, and the target host port became reachable after the Compose
network was changed to a unique experiment network. The prior stale network
had no attached containers and caused the first healthy target to be
host-unreachable. No volume deletion, prune, factory reset, or unrelated
container cleanup was performed.

## 15. Event/Observability Quality

The capture implementation now records redacted controller events, streamed
Agents API events, per-turn event slices, retrieved session items, terminal
turn outcome, approval, remediation, and verification records. Final turn
Markdown is extracted from the latest completed assistant Session Item rather
than concatenated from streaming deltas. Text artifacts and JSONL events scrub
credential assignments and signed URLs embedded in free-form text. The
deterministic tests verified artifact persistence, field-aware redaction,
credential separation, approval denial, saved-agent payload construction, and
final-item extraction.
No live Agents API JSONL stream was produced because credential readiness failed
before session creation. Local controller and target evidence was captured in
the ignored run directory and summarized in the tracked review evidence.

The local console adds a separate SSE stream for sanitized controller lifecycle
events. Browser-visible evidence is labelled as observed, controller-owned, or
reserved for a future live Agent run; it does not present private model
chain-of-thought as UI content.

## 16. Failures and Limitations

The implementation audit found that the prior controller incorrectly reused
`OPENAI_API_KEY` as the executor credential. That is corrected: the host
controller requires `OPENAI_API_KEY`, the executor requires a separate
`OPENAI_EXECUTOR_API_KEY`, and only the latter is mapped to `CODEX_API_KEY`.
The saved agent and project identifiers are now supplied as local runtime
identifiers rather than committed source values. No credential was persisted.
The independent review's remediation reset bug, free-text redaction gap,
repeated-evidence gap, workspace hostname mismatch, and final-response
extraction issue are corrected. The executor image records the installed
`codex-cli 0.156.0-alpha.9` version in its runtime log; the Dockerfile still
intentionally follows the alpha channel.

Observed blockers on 2026-09-20:

- `OPENAI_API_KEY` and `OPENAI_EXECUTOR_API_KEY` were both missing in the
  invoking environment. No session request was attempted.
- Docker Desktop 29.8.0 on `aarch64` initially left containers in `Created`,
  then passed the busybox smoke test after recovery. A stale network/project
  ownership conflict was resolved by using a unique experiment network.
- The host `Documents` worktree also became content-read-inaccessible to shell
  commands during this run. The implementation branch was prepared in a
  disposable `/tmp` clone from the exact `develop` commit to avoid overwriting
  the user worktree. The original worktree must be rechecked after local file
  access is restored.

The approved-remediation Docker integration test passed on 2026-09-21: a
fault checkout returned 504, the controller restored the checked-in safe
configuration with explicit approval, recreated only the target with the reset
flag disabled, and a subsequent checkout returned 200. No Agents API session
was created during this validation.

## 17. Files Changed

The relevant implementation changes are under `.gitignore`, `README.md`,
`.env.example`, `artifacts/README.md`, `controller/`, `docker-compose.yml`,
`fixtures/incident_timeline.json`, `sre_environment/`, `target_service/`, and
`tests/`. This branch additionally adds `UI_SPEC.md`, `ui/`,
`controller/web_api.py`, `controller/requirements-ui.txt`,
`scripts/start_sre_ui.sh`, and `tests/test_web_api.py`. Generated runtime
outputs remain under ignored `artifacts/` paths.
`AUDIT_FINDINGS.md` records the pre-fix audit in the original local worktree and
must be reconciled before relying on that worktree's branch state.

## 18. Exact Reproduction Commands

```bash
cd /Users/ting/Documents/New\ project/armie-operational-intelligence
python3 -m unittest discover -s tests -v
ARMIE_RUN_DOCKER_INTEGRATION=1 python3 -m unittest tests.test_docker_integration -v
python3 -m compileall -q controller target_service tests
docker version --format 'client={{.Client.Version}} server={{.Server.Version}}'
docker context show
docker info --format 'server={{.ServerVersion}} os={{.OperatingSystem}} arch={{.Architecture}} running={{.ContainersRunning}} stopped={{.ContainersStopped}} images={{.Images}} driver={{.Driver}}'
docker run --rm busybox:latest echo docker-ok
python3 -m controller.cli prepare
docker compose up -d target
python3 -m controller.cli probe
curl -fsS http://127.0.0.1:18080/diagnostics/timeline
python3 -m venv .ui-venv
.ui-venv/bin/python -m pip install -r controller/requirements-ui.txt
npm ci --prefix experiments/openai-agents-sre-local-spike/ui
.ui-venv/bin/python -m uvicorn controller.web_api:app --app-dir . --host 127.0.0.1 --port 8787
npm --prefix experiments/openai-agents-sre-local-spike/ui run dev -- --host 127.0.0.1 --port 5173
# Open http://127.0.0.1:5173 and click Start local validation.
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

Factual observation at this boundary: the code path, deterministic tests,
Docker incident, controlled approved remediation, and fresh contradiction
evidence are demonstrated. The browser console is also locally demonstrated,
but the Agents API completion gate is not satisfied.
A follow-up run must set both credentials and runtime identifiers locally,
create a real session, and capture the full same-session trace before this
report can be marked complete. This spike does not decide the final ARMIE
architecture or recommend production adoption.
