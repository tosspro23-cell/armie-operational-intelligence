# ARMIE Operational Intelligence

## Architecture Spike #001 — OpenAI Agents API local SRE investigation

This repository contains one isolated experiment. It is not an ARMIE platform
redesign and it does not introduce an orchestration framework.

The runtime has three deliberately separate components:

1. Codex implements and runs the experiment.
2. `synthetic-payment-api` is an ordinary FastAPI service with a deterministic
   checkout incident.
3. The saved OpenAI SRE agent runs as a Managed Agents API session.

The SRE session uses the current self-hosted environment mechanism. A local
`codex exec-server` runs inside a Docker container with a read-only workspace
and no Docker socket. The controller owns the human approval gate and exposes
only one experiment-specific remediation: restore the known-safe runtime
configuration and restart the synthetic target container.

## Current execution status

Docker, the deterministic local incident, and real saved-agent acceptance runs
have been demonstrated. The latest run was started from the browser Workbench
button and completed the same-session approval continuation and
post-remediation verification. The purple Agents API Control Room now groups
Session identity, investigation turns, approval, controlled remediation,
verification, and observable controller events; the blue Payment API Workspace
groups customer impact and service evidence. Do not infer live completion from
a green unit-test or frontend build alone.

## Prerequisites

- Python 3.11+ for the controller and tests.
- Docker Desktop with permission to access its Docker socket.
- `OPENAI_API_KEY` exported in the invoking shell for the host-side controller.
  It must be allowed to read/write Agents API sessions and write responses
  (`api.agents.read`, `api.agents.write`, and `api.responses.write`). It is
  never passed to the executor.
- `OPENAI_EXECUTOR_API_KEY` exported in the invoking shell as a separate,
  restricted Agents environment key. It must belong to the same organization,
  project, and identity scope as the session. It is passed to the executor
  only as `CODEX_API_KEY`.
- `ARMIE_SRE_AGENT_ID` and `OPENAI_PROJECT_ID` set locally to the saved agent
  and project identifiers supplied for this spike. They are non-secret runtime
  identifiers and are intentionally not committed to source.
- A valid `gh` authentication if the repository is to be created on GitHub.

## Run the deterministic checks

```bash
cd /path/to/armie-operational-intelligence
python3 -m unittest discover -s tests -v
```

The tests do not call OpenAI and do not replace the real acceptance run.

## Open the local SRE Console

The UI is a presentation and control layer over the local Controller. The
browser never receives credentials, Docker access, or arbitrary command
capabilities. It can run either of two deliberately separate modes:

- **Start local validation** runs the deterministic controller-only proof. It
  is useful for demonstrating the payment symptom and read-only evidence
  boundary without API usage.
- **Start Agents API investigation** starts one real Session from the saved SRE
  Agent, connects the self-hosted executor in Docker, streams observable
  session evidence, pauses at the human approval gate, and continues the same
  Session through controlled remediation and independent verification.

From the repository root, install the isolated UI dependencies once:

```bash
python3 -m venv .ui-venv
.ui-venv/bin/python -m pip install -r controller/requirements-ui.txt
npm ci --prefix experiments/openai-agents-sre-local-spike/ui
```

Then start both local processes with:

```bash
./scripts/start_sre_ui.sh
```

Open <http://127.0.0.1:5173>. For the real live demonstration, choose
**Start Agents API investigation**. The page will reproduce the checkout
fault, create the real Session, show the investigation turns and event
metadata, present the evidence-backed proposal, and enable Approve/Deny only
while the live run is waiting for a decision. After approval, the same Session
must inspect new health, checkout, metrics, and log evidence before the page
shows recovery.

The **Reset fault** action is a preparation step, not another validation run:
it recreates the target with the deterministic fault and leaves the target in
`Fault ready`, so **Start Agents API investigation** becomes available without
requiring terminal commands. The blue payment controls and evidence panels are
the synthetic service workspace; the purple Agents API Control Room owns the
Session, investigation turns, proposal, approval, event stream, and
same-session recovery check.

After a completed run, the purple control room retains that Session as
historical review evidence. The incident header and blue Payment API Workspace
always show the target's current Controller state, so a later **Reset fault**
cannot be confused with the previous run's recovered HTTP 200 result.

The credentials are loaded by the local Controller process from the ignored
`.env.local` when present. They are never sent to the browser. The terminal CLI
remains available as a diagnostic fallback, but it is no longer required for
the normal customer-facing demonstration.

## Prepare and run the local service

```bash
python3 -m controller.cli prepare
docker compose up -d target
curl -fsS http://127.0.0.1:18080/health
python3 -m controller.cli probe
```

By default the controller rebuilds the experiment images before a probe or
acceptance run. If Docker Hub is temporarily unavailable and the required
experiment images are already present locally, set
`ARMIE_REUSE_LOCAL_IMAGES=1` for that run to use Compose `--no-build`. This is
an explicit local-runtime fallback; it does not alter the image definitions.
The browser launcher applies this local-image fallback by default so that
Workbench Reset and local validation do not unexpectedly depend on Docker Hub.
Set `ARMIE_REUSE_LOCAL_IMAGES=0` before starting the launcher when an explicit
image rebuild is required.

The service writes structured logs and metrics to a Docker named volume shared
read-only with the executor. The controller snapshots that volume to
`artifacts/runs/<run-id>/runtime/` and `artifacts/runtime/` after probing.
`probe` confirms the deterministic checkout fault with real HTTP requests.

## Run the real Agents API spike

```bash
export OPENAI_API_KEY='...'
export OPENAI_EXECUTOR_API_KEY='...'
export ARMIE_SRE_AGENT_ID='agent-id-from-the-spike-brief'
export OPENAI_PROJECT_ID='project-id-from-the-spike-brief'
python3 -m controller.cli run
```

The controller will:

- prepare and start the target service;
- create a real session using the saved agent ID supplied through
  `ARMIE_SRE_AGENT_ID`;
- apply the requested session overrides, including the current saved-agent
  model `gpt-6-luna`;
- connect the self-hosted executor inside Docker;
- send the initial investigation request without pasting the evidence;
- record streamed events and tool activity;
- send a read-only contradictory observation to the same session;
- request a revised assessment and a bounded remediation proposal; and
- stop at `Approve proposed remediation? [y/N]`.

Approval defaults to **NO**. With a human explicitly approving in the CLI,
the controller executes only the fixed safe-config restoration and target-only
restart, then asks the same session to inspect actual recovery evidence. It
does not execute arbitrary agent-provided commands.

For a non-interactive run, the approval gate records a denied decision. An
explicit human-controlled approval can use:

```bash
python3 -m controller.cli run --approve-remediation
```

That flag is intentionally explicit and still performs the same fixed action.
Never put either key in a tracked `.env` file. If a local `.env` file is used
by a shell wrapper, keep it ignored and restrict its permissions.

## Artifacts

Each run is written to `artifacts/runs/<run-id>/`; see
[`artifacts/README.md`](artifacts/README.md) for the schema. Generated runtime
files are gitignored. The report must distinguish API-observed events from
controller observations and ground truth known only to the experiment.

## Official documentation used

- [Agents API overview](https://developers.openai.com/api/docs/guides/agents-api/overview)
- [Run and continue sessions](https://developers.openai.com/api/docs/guides/agents-api/sessions)
- [Events and items](https://developers.openai.com/api/docs/guides/agents-api/sessions/events)
- [Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)
- [Create an agent session](https://developers.openai.com/api/reference/python/resources/beta/subresources/agents/subresources/sessions/methods/create)
