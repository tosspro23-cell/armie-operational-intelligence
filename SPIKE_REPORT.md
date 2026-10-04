# ARMIE Architecture Spike #001 — OpenAI Agents API local SRE runtime

Status: Docker, the local synthetic incident, a real Agents API session, the
self-hosted environment connection, multi-turn investigation, contradiction
reassessment, explicit approval, controlled remediation, and same-session
post-remediation verification are live-demonstrated. The live run used the
saved Agent in the ARMIE Operational Intelligence project with model
`gpt-6-luna`; no replacement Agent was created. Session and environment IDs
are retained in ignored raw artifacts and redacted review evidence.

This branch also adds a local-only Vite/React console over the existing FastAPI
controller. It has been built and opened against a real Docker target; it shows
the customer-facing payment failure, fault evidence, controller SSE events, and
approval boundary. Its fixed `ui-demo-order` request returned a real synthetic
HTTP 504 and emitted a `payment.checkout.simulated` controller event. The
Workbench now also provides a bounded browser start action for a real Agents
API Session. The latest browser-triggered path was exercised end to end in run
`20261003T011902Z`, including Session creation, environment connection,
contradiction reassessment, explicit approval, controlled remediation, and
same-Session recovery verification. The earlier completed browser run remains
in the ignored runtime history for comparison.
The Workbench control surface is grouped into an Incident Workspace for the
synthetic payment service and a purple Agents API Control Room for Session
start, observable turns, approval, event stream, and same-session recovery.
Reset fault is now a separate preparation action: it recreates the deterministic
fault and leaves the local target in `fault_ready`, making a new Agents API run
available without another terminal command. Local actions hide any historical
live-run view so old recovery evidence cannot be mistaken for the current
faulted target.

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

The live mode adds the Agents API event stream and same-session continuation
behind this same controller boundary. The purple Agents API Control Room
exposes the current proposal and approval action only while the live run is
actually waiting at the approval boundary, then keeps the recovery check and
observable controller stream in the same visual boundary.

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

The latest browser-triggered live run (`20261003T011902Z`) created one real
Session and connected one self-hosted environment. The same Session was used
for all four captured turns:

| Turn | Captured event records | Retrieved Session Items | Outcome |
| --- | ---: | ---: | --- |
| initial investigation | 2,245 | captured | completed |
| contradictory-evidence reassessment | 1,139 | captured | completed |
| remediation proposal | 794 | captured | completed |
| post-remediation verification | 1,190 | captured | completed |

The controller captured environment connection events, streamed events,
turn outcomes, tool and shell interaction records, retrieved items, and final
assistant Session Items. The initial investigation and reassessment were
read-only. The proposal turn stopped before any mutation; the later mutation
was started only by the explicit approval continuation.

## 6. Hypotheses Generated

The Agent considered two plausible explanations: a recent deployment or
application configuration regression, and downstream latency or pressure.
The evidence supported a direct timeout mechanism: dependency latency was 168
ms while the active checkout budget was 120 ms. The initial deployment
explanation remained plausible as a trigger or contributor, but the later
timeline evidence showed that the tight budget predated the deployment and
that a prior 118 ms response had succeeded.

## 7. Evidence Gathered

The live target returned health 200 and eight real fault checkout responses
with status 504, followed by a post-remediation HTTP 200 response. The
downstream diagnostic reported status `ok`, latency 168 ms, and a warning
threshold of 150 ms. The fault sample recorded eight attempts and eight
timeouts. Structured JSONL logs, deployment metadata, runtime configuration,
and the runbook were read from the running container. The executor boundary
check reached the target, read the evidence volume, and was denied write access
by the read-only mount. A target force-recreate with the fault fixture produced
the same timeout again. After explicit approval, the target-only controlled
restart restored the safe 300 ms timeout; the Agent then observed health 200,
checkout 200, a ready checkout path, and fresh metrics with two attempts, two
successes, and zero timeouts in its verification sample.

## 8. Hypothesis Revision Test

The controller obtained a fresh read-only timeline diagnostic and sent it to the
same Session. The Agent recalibrated its explanation toward the latency crossing
the existing timeout budget rather than treating the deployment as sufficient
causal proof. It retained the deployment as a possible contributor, reported
the remaining uncertainty, and requested the safest next step: inspect the
current evidence and propose a bounded mitigation without making an unapproved
change.

## 9. Human Approval Behavior

The controller prints `Approve proposed remediation? [y/N]`. Empty input,
`N`, unexpected input, and non-interactive execution default to denied. The
Workbench now shows Approve and Deny only when the real live run is waiting at
`approval_pending`; those buttons resume the same Session through the bounded
controller path. No mutation is permitted before an explicit approval event.
The user explicitly approved this synthetic remediation in the continuation
turn. A later duplicate Workbench approval request returned HTTP 409 because
the run was already completed, so it could not execute a second mutation.

## 10. Remediation and Verification

The user approved the live proposal explicitly. The controller executed only
the allowlisted action: restore the known-safe synthetic configuration and
recreate the target with `RESET_RUNTIME_CONFIG=0`; no Docker socket or
arbitrary host command was exposed to the Agent. The same Session then ran a
post-remediation verification turn and independently inspected health,
checkout, metrics, runtime configuration, and logs. It observed HTTP 200
checkout recovery and zero timeouts in its short sample. Remaining uncertainty
is recorded: observed dependency latency was still 168 ms, above the 150 ms
warning threshold; the verification sample was small; and the deployment ID
retained in evidence differs from the active service version. No production
system was changed.

## 11. Session Persistence Observations

The initial investigation, contradiction, proposal, approval continuation, and
post-remediation verification all use the same Session ID and the same
environment ID. The controller retrieved the Session again before continuing
and refused to proceed if the returned ID differed. After the original CLI
process ended, the resume path reattached the already-running executor instead
of creating a new environment or Session.

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

The capture implementation records redacted controller events, streamed Agents
API events, per-turn event slices, retrieved session items, terminal turn
outcome, approval, remediation, and verification records. Final turn
Markdown is extracted from the latest completed assistant Session Item rather
than concatenated from streaming deltas. Text artifacts and JSONL events scrub
credential assignments and signed URLs embedded in free-form text. The
deterministic tests verified artifact persistence, field-aware redaction,
credential separation, approval denial, saved-agent payload construction, and
final-item extraction.
The latest live raw JSONL stream and per-turn artifacts are under the ignored
run directory `artifacts/runs/20261003T011902Z/`; sanitized summaries and redacted
metadata are committed under the review directory. The UI presents observable
event and final-output evidence, not private hidden chain-of-thought.

The local console adds a separate SSE stream for sanitized controller lifecycle
events. Browser-visible evidence is labelled as observed, controller-owned, or
live Session evidence; it does not present private model chain-of-thought as UI
content. The customer payment surface uses the same
observed checkout envelope to present a business-level failure first and a
technical detail dialog second; the browser still calls only the local
controller's fixed checkout route. A browser-level reset and payment probe were
also re-run on this branch: the target reached `Fault ready`, the probe returned
HTTP 504 with `checkout_dependency_timeout`, and the Agents API start control
became available while the old live-run view was hidden. The subsequent browser
start is recorded as `workbench_live_run_requested` with `entrypoint=browser`
in the latest controller event artifact.

A 2026-10-03 revalidation found that a completed Session's recovered target
snapshot could visually override a newly reset current target. The UI now keeps
completed Session evidence in the purple control room while the incident header
and Payment API Workspace always use the current Controller target. Browser
verification showed `Fault ready` and HTTP 504 alongside separately labelled
retained Session evidence.

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

Historical blockers and operational limitations:

- `OPENAI_API_KEY` and `OPENAI_EXECUTOR_API_KEY` were both missing in the
  invoking environment. No session request was attempted.
- On 2026-09-30 both credentials were present and the newly selected project
  could not resolve the previous saved-agent ID. The API returned HTTP 404 with
  `No persisted agent found`. That historical attempt stopped safely before
  session creation. The correct-project Agent was subsequently configured and
  used for the live run; no replacement Agent was created in the experiment.
- Docker Desktop 29.8.0 on `aarch64` initially left containers in `Created`,
  then passed the busybox smoke test after recovery. A stale network/project
  ownership conflict was resolved by using a unique experiment network.
- The host `Documents` worktree also became content-read-inaccessible to shell
  commands during this run. The implementation branch was prepared in a
  separate worktree from the exact `develop` commit to avoid overwriting the
  user worktree. Access is working in the current revalidation worktree.

The approved-remediation Docker integration test passed on 2026-09-21. The
real live run then passed the same boundary with explicit user approval and
same-session Agent verification. During resume, Compose `ps -q` did not list
the one-off executor container, so the controller safely stopped before
mutation; the fallback label-based lookup was added and the subsequent resume
succeeded. This is an operational limitation of the local one-off Compose
lifecycle, not evidence of a second Session.

An earlier retained live stream contains one API `internal_error` event after
all four top-level turns had completed and after remediation verification.
Revalidation also found executor containers from completed runs still running.
These were cleanup defects, not turn failures. The latest browser run has four
completed and zero failed/cancelled top-level turns. The controller now closes
each SSE response explicitly and assigns/removes an exact per-run executor
container, with deterministic coverage. Final inspection nevertheless found
the latest one-off executor still running until it was stopped by an explicit
operator cleanup; end-to-end post-run executor cleanup remains a limitation,
not a claimed live success.

## 17. Files Changed

The relevant implementation changes are under `.gitignore`, `README.md`,
`.env.example`, `artifacts/README.md`, `controller/`, `docker-compose.yml`,
`fixtures/incident_timeline.json`, `sre_environment/`, `target_service/`, and
`tests/`. This branch additionally adds `UI_SPEC.md`, `ui/`,
`controller/web_api.py`, `controller/requirements-ui.txt`,
`scripts/start_sre_ui.sh`, `tests/test_web_api.py`, and the source-label fix in
`controller/cli.py`. Generated runtime
outputs remain under ignored `artifacts/` paths.
`AUDIT_FINDINGS.md` records the pre-fix audit in the original local worktree and
must be reconciled before relying on that worktree's branch state.

## 18. Exact Reproduction Commands

```bash
cd /path/to/armie-operational-intelligence
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
ARMIE_REUSE_LOCAL_IMAGES=1 \
  .ui-venv/bin/python -m controller.cli probe
export OPENAI_API_KEY='...'
export OPENAI_EXECUTOR_API_KEY='...'
export ARMIE_SRE_AGENT_ID='...'
export OPENAI_PROJECT_ID='...'
ARMIE_REUSE_LOCAL_IMAGES=1 python3 -m controller.cli run
# Resume an existing approval-pending live run after an explicit human decision.
.ui-venv/bin/python -m controller.cli resume --run-id <approval-pending-run-id> --approve-remediation --keep-target
./scripts/start_sre_ui.sh
```

The last command must be run by a human who understands the approval boundary,
after Docker can start containers, both credential variables are set, and the
non-secret runtime identifiers are set. The values must never be pasted into
the Codex conversation.

## 19. Architecture Observations

Factual observation at this boundary: the local target, self-hosted executor,
real managed Agent session, multiple investigation turns, contradiction test,
explicit approval, controlled target-only remediation, and same-session
post-remediation verification are demonstrated. Multiple complete live runs
are retained in the local evidence history, including the latest
browser-triggered run. The Workbench exposes the approval step only for a
pending same-session
run and shows the before/after evidence after completion. The result is
limited to this isolated synthetic experiment and does not decide the final
ARMIE architecture or recommend production adoption.
