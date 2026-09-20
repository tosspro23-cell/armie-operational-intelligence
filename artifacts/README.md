# Runtime artifact schema

Runtime outputs are intentionally not committed. A run directory is named
`artifacts/runs/<UTC-run-id>/` and contains:

- `runtime_identity.json`: git commit, experiment version, target/deployment
  versions, agent ID, model, environment type, and session ID when known.
- `controller_events.jsonl`: controller lifecycle, API request/response
  metadata, approval decision, remediation, and verification records.
- `agents_api_events.jsonl`: every observable SSE event payload from the Agents
  API, with local capture time and elapsed milliseconds.
- `executor.log`: stdout/stderr from the isolated `codex exec-server` Docker
  process. Credentials are never written to this file.
- `target_probe.jsonl`: actual HTTP responses used to prove health, fault, and
  post-remediation state.
- `session.json`: the API's session creation response after redaction of
  secret-shaped values.
- `agent_turns.md`: compact extracted model text for human review; the raw
  event stream remains authoritative.

The target service writes `service.jsonl`, `metrics.json`, and
`runtime_config.json` to the Docker named volume shared read-only with the
executor. The controller snapshots them to `artifacts/runtime/` and each run's
`runtime/` directory. These are generated evidence, not fixtures.

The controller redacts secret-shaped values before JSONL persistence and never
logs request authorization headers or environment variable values.
