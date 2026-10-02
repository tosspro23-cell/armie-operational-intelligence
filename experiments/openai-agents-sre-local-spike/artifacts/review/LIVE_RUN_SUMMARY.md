# Live Run Summary

Status: the real Agents API architecture spike completed for the isolated
synthetic service. The run created one Session from the saved correct-project
Agent, connected one self-hosted executor, completed four turns, reached the
human approval boundary, executed the allowlisted target-only remediation after
explicit approval, and verified recovery in the same Session. No production
system was changed.

Reviewed branch base: `develop` at `80c4c43`.
Validation branch: `spike/openai-agents-sre-local-ui`.
Live run: `20261001T185830Z`.

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
- The real Session used saved Agent `SRE agent for incident response` with
  model `gpt-6-luna`; stable redacted labels are `sess_…5c9ded80fe` and
  `ccarenv_…NDg3MTc1YQ`.
- The same Session completed initial investigation, contradiction reassessment,
  remediation proposal, and post-remediation verification. Per-turn event
  counts were 2363, 694, 813, and 1679; retrieved item counts were 25, 29, 34,
  and 64.
- After explicit approval, the safe 300 ms configuration was restored and the
  Agent observed HTTP 200 checkout, health 200, and zero timeouts in its fresh
  verification sample.
- The user approval is recorded in the run artifact. A later duplicate approval
  request was rejected with HTTP 409 because the run was already complete.
- The earlier 2026-09-30 saved-agent/project mismatch remains preserved as a
  historical ignored run; it is not the result of this completed run.

## Completion gate

Demonstrated for the isolated experiment: local target execution, deterministic
fault, real saved-Agent Session, self-hosted environment connection, real
read-only evidence inspection, multiple turns, contradiction reassessment,
explicit approval before mutation, allowlisted remediation, and independent
same-session verification. Remaining limitations are the short post-change
sample, the still-elevated synthetic downstream latency, and the known
deployment/version metadata ambiguity recorded by the Agent.
