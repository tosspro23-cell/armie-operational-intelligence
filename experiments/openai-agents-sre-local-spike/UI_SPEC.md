# ARMIE SRE Local Console — UI Specification

## Status

First implementation slice: local deterministic validation only. The OpenAI
Agents API session is not created by this UI slice.

## Objective

Provide a professional, inspectable browser interface for the existing local
SRE architecture spike. The console must make the synthetic incident,
evidence, controller actions, approval boundary, and recovery visible without
changing the runtime topology or inventing Agent activity.

## Scope

The first slice exposes:

- target health, checkout behavior, metrics, downstream diagnostics, and the
  fresh timeline observation;
- a customer-facing payment simulation surface that calls one fixed synthetic
  checkout through the controller and translates an observed failure into a
  clear payment error state;
- structured runtime logs, runtime configuration, deployment metadata, and
  runbook content;
- an explicit local validation lifecycle;
- a controller-owned, allowlisted remediation proposal and approval gate;
- before/after recovery evidence;
- append-only UI lifecycle events delivered through Server-Sent Events (SSE);
- an Agent API readiness panel that clearly reports `not_connected` until a
  real session is created.

The later live slice will add the real Agents API session event stream,
environment connection state, Agent output, reasoning summaries, command/tool
items, turn outcomes, contradiction reassessment, and same-session
verification. It will reuse the same event and evidence contracts.

## Non-goals

- no ARMIE platform redesign;
- no new multi-agent orchestration framework;
- no direct browser access to Docker or OpenAI credentials;
- no arbitrary command endpoint;
- no presentation of private model chain-of-thought;
- no synthetic Agent output in place of live API evidence;
- no public hosting or production access.

## Topology

```text
React/Vite browser UI :5173
        |
        | local HTTP control + SSE event stream
        v
FastAPI controller :8787 (127.0.0.1 only)
        |
        +--> synthetic-payment-api Docker target :18080
        +--> sanitized local artifacts and Docker evidence
        +--> later: Agents API session event stream
```

The browser is a presentation and intent surface. The Controller is the only
component allowed to perform target lifecycle operations or the controlled
remediation. The UI backend uses fixed subprocess argument lists and never
accepts arbitrary shell commands.

## Evidence provenance

Every displayed item belongs to one of these classes:

- `observed`: returned by the running target or read from its evidence volume;
- `controller`: an action or state transition recorded by this repository;
- `agent`: an event or item returned by the Agents API;
- `ground_truth`: experiment-side fact, hidden from the initial Agent request.

The first UI slice must not label controller observations as Agent reasoning.

## Lifecycle states

```text
idle
  -> target_starting
  -> incident_reproduced
  -> evidence_available
  -> approval_required
  -> remediation_running
  -> verification_complete
```

The live Agent slice will insert `investigation_running`,
`contradiction_pending`, `reassessment_complete`, and
`proposal_ready` before `approval_required`.

## Controller API

All routes are local-only and return sanitized JSON.

- `GET /api/state`: complete current console state;
- `GET /api/health`: backend readiness and target reachability;
- `GET /api/evidence/logs?limit=N`: structured target log tail;
- `GET /api/evidence/config`: runtime config, deployment, and runbook;
- `GET /api/events`: current event snapshot;
- `GET /api/events/stream`: SSE lifecycle events;
- `POST /api/checkout/simulate`: run one fixed local test payment through the
  controller and return the observed checkout/metrics envelope;
- `POST /api/local/start`: start the target and run real local probes;
- `POST /api/approval`: approve or deny the current fixed remediation proposal;
- `POST /api/local/reset`: restore the initial deterministic fault state;
- `POST /api/local/stop`: stop only the experiment target.

`POST /api/approval` accepts only the current proposal identifier and the
decisions `approve` or `deny`. Approval is denied by default and cannot invoke
an arbitrary action.

## UI layout

1. **Environment header** — local-only banner, target state, run ID, commit,
   and Agent readiness.
2. **Incident overview** — health, checkout status, error code, dependency
   latency, timeout budget, and severity.
3. **Timeline** — deployment, degradation, observed errors, contradiction,
   approval, remediation, and verification events.
4. **Evidence workspace** — tabs for logs, metrics, config, deployment,
   runbook, and timeline evidence.
5. **Investigation panel** — local mode shows `Agent API not connected`; live
   mode will show Agent events, tool calls, command results, final output, and
   reasoning summaries with provenance labels.
6. **Approval and recovery panel** — action, risks, verification, rollback,
   explicit approval, and before/after evidence.

## Interaction rules

- failed checkout must be visible as an HTTP status and structured error code;
- the customer-facing payment surface must make the business symptom visible
  before showing the technical status, and its detail dialog must identify the
  response as synthetic local evidence;
- raw JSON remains available behind an expandable evidence view;
- red/amber/green are supplemented with text labels and icons;
- no UI state may imply recovery until a new HTTP checkout and new metrics/log
  evidence confirm it;
- event stream reconnects must recover from `/api/state` and `/api/events`;
- credentials, Authorization headers, executor remote URLs, and full process
  environments never reach the browser.

## Acceptance criteria for this slice

- a user can open the UI locally and see the target's real fault;
- clicking **Start local validation** causes real target probes and updates the
  UI through SSE;
- logs, metrics, config, deployment metadata, runbook, and timeline are
  inspectable;
- the UI clearly says the Agent API is not connected;
- the remediation proposal is visible but no mutation occurs before approval;
- deny and empty/default approval remain safe;
- explicit approval executes only the known-safe experiment remediation;
- the UI shows a new HTTP 200 checkout and updated evidence after recovery;
- no credentials or arbitrary command capability are exposed;
- backend deterministic tests and a browser build pass.
