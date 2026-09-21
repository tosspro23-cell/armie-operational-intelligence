# Live Run Summary

Status: independent-review implementation fixes passed deterministic checks and
local Docker validation, including approved-remediation recovery; the live
Agents API run remains blocked at credential readiness before session creation.

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
- Presence-only credential check: `OPENAI_API_KEY=missing`; `OPENAI_EXECUTOR_API_KEY=missing`.
- The controller acceptance command stopped at its real credential boundary with exit code 2 and persisted the partial ignored run under `artifacts/runs/20260920T205621Z/`.
- No Agents API session, session ID, environment connection, turn, model output, tool result, approval recommendation, remediation, or verification was fabricated.

## Completion gate

Not satisfied. The next safe action is to provide the two credentials locally
and rerun `python3 -m controller.cli run`; do not paste either credential into
chat. The CLI will create the real session, connect the executor, and stop at
the explicit approval prompt.
