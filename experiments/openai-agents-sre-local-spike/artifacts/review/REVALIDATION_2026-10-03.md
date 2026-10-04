# Revalidation — 2026-10-03

This review distinguishes the read-only checks from the completed live runs.
The latest browser-triggered completion is retained under
`artifacts/runs/20261003T011902Z/`.

## Current source and deterministic checks

- Reviewed branch: `spike/openai-agents-sre-local-ui`.
- Starting commit: `67a7c04264411acf073e74383b90ff01f0515379`.
- Python tests: 35 passed, with the separately executed Docker integration
  test skipped in the default suite.
- Opt-in Docker remediation integration: passed independently.
- Python compile check: passed.
- Vite/TypeScript production build: passed.
- Git diff whitespace check: passed before fixes.

## Docker and local target

- Docker client/server: 29.8.1, context `desktop-linux`.
- Disposable `busybox` test printed `docker-ok`.
- Target health returned HTTP 200 and reported checkout degraded.
- A fixed synthetic checkout returned HTTP 504 with
  `checkout_dependency_timeout`.
- The opt-in integration test reproduced 504, enforced explicit approval,
  applied the allowlisted target-only remediation, and observed HTTP 200.
- Three executor containers left by completed historical runs were found and
  removed. They had no persistent experiment evidence and no Docker socket.

## Agents API read-only online checks

- Stored Session retrieval: HTTP 200; stored Session and Agent identities
  matched; Session status was `idle`; environment type was `self_hosted`.
- Saved Session items retrieval: HTTP 200; 57 items; no additional page.
- Saved Agent retrieval: HTTP 200; identity matched; name was
  `SRE agent for incident response`; model was `gpt-6-luna`.
- No new Session, turn, approval, remediation, or model inference was created.

The current official Agents API documentation was also checked. It still
requires a separate restricted environment key passed as `CODEX_API_KEY`, the
returned remote URL to be used unchanged with its per-Session environment ID,
the event stream to be open before sending work, an observed
`agent.session.environment.connected` event, and explicit terminal turn outcome
handling. The implementation continues to follow those requirements.

## Earlier retained live evidence invariants

- 5,478 streamed Agents API events.
- One distinct Session ID across all retained events.
- One observed environment-connected event.
- Four completed top-level turns; zero failed/cancelled top-level turns.
- Approval was recorded before the first remediation mutation event.
- Checkout sequence: eight HTTP 504 observations followed by HTTP 200.
- The earlier retained stream had one API `internal_error` after all four
  completed turns and verified remediation. It is preserved as a limitation
  rather than hidden; the latest browser-triggered run has no such event.

## Findings corrected in this revalidation

1. The evidence manifest had a stale checksum for `security-scan.txt`.
2. Completed runs could leave the SSE reader and executor container alive.
3. After Reset, completed Session recovery evidence could override the current
   target's HTTP 504 in the blue Payment API Workspace.
4. The approval evidence used an imprecise decision-source label.
5. SPIKE_REPORT referenced the earlier raw run instead of the latest browser
   run.

The controller now closes the SSE response, removes only its exact per-run
executor container, and has deterministic regression tests. The Workbench now
labels the previous Session as retained evidence and always renders the current
Controller target in the incident and payment regions.

## Remaining limitations

- The cleanup boundary is deterministic-tested. The latest paid Agents API
  Session completed all four top-level turns, but final inspection found its
  one-off executor still running; that exact experiment container was then
  stopped explicitly. End-to-end post-run executor cleanup is not claimed.
- The recovery sample is short and synthetic; it is not production evidence.
- Dependency latency remains elevated in the synthetic fixture.
- The retained verification correctly records a `.1` service version with a
  `.2` deployment identifier after rollback; that metadata ambiguity remains
  visible and should not be presented as reconciled.
- Public readiness remains conditional because reachable history contains
  host-specific path examples and local author metadata. Repository visibility
  was not changed.

## Post-approval completion — 2026-10-04

- The Workbench browser approval resumed the pending stored Session
  `sess_…849611c13a`; it did not create a replacement Session.
- The resumed Session reconnected the self-hosted executor, recorded explicit
  approval before mutation, restored the checked-in 300 ms runtime configuration,
  restarted only the synthetic target, and continued the same Session.
- The latest run `20261003T011902Z` completed all four turns: initial
  investigation (2,245 events), contradictory-evidence reassessment (1,139),
  remediation proposal (794), and post-remediation verification (1,190).
- The verification turn independently observed health HTTP 200, checkout HTTP
  200 with `authorized` and no error code, two attempts, two successes, zero
  timeouts, new recovery logs, and the restored 300 ms configuration. Downstream
  latency remained 168 ms, above the 150 ms warning threshold.
- The latest raw run shows no failed or cancelled top-level turn. It provides
  direct evidence for the lifecycle: approval → controlled mutation → new
  system evidence → same-Session verification.

## Workbench trigger separation recheck — 2026-10-04

- The reported behavior was reproduced from the controller state: local
  validation had incorrectly entered `approval_required` and created a
  `controller_demo` proposal, which disabled the separate purple Agent API
  start button. No Agents API Session was created by that local path.
- The controller/UI fix makes local validation evidence-only. Its completed
  run `20261004T140554Z` reached `fault_ready`, kept target health at HTTP 200,
  reproduced eight HTTP 504 checkout timeouts, and left `proposal=null` and
  `approval=null`.
- The captured local event sequence included `incident.reproduced`,
  `contradictory.evidence.available`, and `local.validation.completed`; it did
  not include `approval.required`.
- Browser accessibility verification showed the purple action available as
  `Start another investigation`. A real Agents API investigation still
  requires the operator to click that action; approval is shown only after the
  real Session reaches its approval-pending state.
- Deterministic regression coverage now includes
  `test_local_validation_is_evidence_only_and_does_not_request_approval`.

## Workbench Docker recheck — 2026-10-04

- The first UI Reset attempt failed before a new Agent run because the
  Controller inherited the rebuild default and Docker Hub returned an
  authorization/network error resolving `python:3.12-slim`.
- The launcher now defaults to `ARMIE_REUSE_LOCAL_IMAGES=1`, while an explicit
  `ARMIE_REUSE_LOCAL_IMAGES=0` still requests a rebuild.
- A browser-equivalent Reset after the fix reached `fault_ready` with target
  health HTTP 200. The fixed Workbench checkout simulation returned HTTP 504
  with `checkout_dependency_timeout`, and the target container remained
  healthy. No new Agents API Session was created during this recheck.
