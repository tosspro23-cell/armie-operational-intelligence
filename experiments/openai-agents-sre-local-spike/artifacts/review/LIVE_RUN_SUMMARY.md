# Live Run Summary

Status: independent-review implementation fixes passed deterministic checks and
local Docker validation, including approved-remediation recovery. A credentialed
Agents API attempt was made on 2026-09-30 and stopped at session creation
because the configured project cannot resolve the saved agent. No session was
created and no live agent result is claimed.

Reviewed branch base: `develop` at `80c4c43`.
Validation branch: `spike/openai-agents-sre-live-validation`.

## Observable results

- `docker run --rm busybox:latest echo docker-ok` printed `docker-ok`.
- Docker Desktop reported client/server `29.8.0`, context `desktop-linux`, architecture `aarch64`, and `overlayfs`.
- Target image built and the running target reported healthy.
- Host `GET /health` returned 200.
- Eight real `POST /checkout` requests returned 504 with `checkout_dependency_timeout`.
- The downstream diagnostic returned `status=ok`, observed latency 168 ms, and warning threshold 150 ms.
- Metrics recorded 8 attempts, 8 timeouts, and 0 successes.
- Structured logs, deployment metadata, runtime configuration, and runbook were read from the container.
- The isolated executor reached the target, read the runtime evidence, and could not write the read-only evidence mount.
- A force-recreate with the fault fixture reproduced the checkout timeout.
- The fresh `/diagnostics/timeline` observation showed checkout 200 at 118 ms
  before the incident and checkout 504 at 168 ms after the dependency slowed,
  while the 120 ms timeout budget predated the deployment.
- The real opt-in Docker remediation integration test verified fault 504,
  explicit approval, target-only recreation with `RESET_RUNTIME_CONFIG=0`, and
  post-restart checkout 200.
- The executor image reported `codex-cli 0.156.0-alpha.9`; the workspace guide
  uses the actual Compose service name `target`.
- The initial presence-only credential check reported both keys missing and
  stopped before a request.
- After both keys were configured locally, the controller sent a real session
  creation request. OpenAI returned HTTP 404 `No persisted agent found` for the
  configured saved-agent reference and stated that session-local agent IDs
  cannot be reused. The partial ignored run is under
  `artifacts/runs/20260930T084958Z/`.
- No session ID, environment ID, environment connection, turn, model output,
  tool result, approval recommendation, remediation, or verification was
  produced. The target was stopped by the controller cleanup path.
- No Agents API session, session ID, environment connection, turn, model output, tool result, approval recommendation, remediation, or verification was fabricated.

## Completion gate

Not satisfied. The next safe action is to use matching controller and
environment keys in the project that owns the saved agent, then rerun the
controller. Do not paste either credential into chat. The current branch must
not create a replacement SRE agent for this spike.
