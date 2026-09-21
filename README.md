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

Source, Docker, and the deterministic local incident validation are implemented
and demonstrated. The real acceptance run is only complete after
`SPIKE_REPORT.md` records an actual session ID and the captured JSONL evidence
under `artifacts/runs/`. The current run stops before session creation when the
two required credentials are missing. Do not infer completion from a green
unit-test or local-service run.

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
cd /Users/ting/Documents/New\ project/armie-operational-intelligence
python3 -m unittest discover -s tests -v
```

The tests do not call OpenAI and do not replace the real acceptance run.

## Prepare and run the local service

```bash
python3 -m controller.cli prepare
docker compose up -d target
curl -fsS http://127.0.0.1:18080/health
python3 -m controller.cli probe
```

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
- apply the requested session overrides, including `gpt-5.6-luna`;
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
