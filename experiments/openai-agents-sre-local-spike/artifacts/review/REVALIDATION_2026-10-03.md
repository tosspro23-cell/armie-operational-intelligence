# Revalidation — 2026-10-03

This review distinguishes today's checks from the completed live run retained
under `artifacts/runs/20261002T200149Z/`.

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

## Retained live evidence invariants

- 5,478 streamed Agents API events.
- One distinct Session ID across all retained events.
- One observed environment-connected event.
- Four completed top-level turns; zero failed/cancelled top-level turns.
- Approval was recorded before the first remediation mutation event.
- Checkout sequence: eight HTTP 504 observations followed by HTTP 200.
- One API `internal_error` occurred after all four completed turns and verified
  remediation. It is preserved as a limitation rather than hidden.

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

- The cleanup fix is deterministic-tested but has not been exercised by a new
  paid Agents API Session run.
- The recovery sample is short and synthetic; it is not production evidence.
- Dependency latency remains elevated in the synthetic fixture.
- The retained verification correctly records a `.1` service version with a
  `.2` deployment identifier after rollback; that metadata ambiguity remains
  visible and should not be presented as reconciled.
- Public readiness remains conditional because reachable history contains
  host-specific path examples and local author metadata. Repository visibility
  was not changed.
