# Runtime artifact schema

Runtime outputs are intentionally not committed. A run directory is named
`artifacts/runs/<UTC-run-id>/` and contains:

- `runtime_identity.json`: git commit, experiment version, target/deployment
  versions, configured model, environment type, and session/environment IDs
  when known. The self-hosted remote URL is deliberately not persisted.
- `controller_events.jsonl`: controller lifecycle, API request/response
  metadata, approval decision, remediation, and verification records.
- `agents_api_events.jsonl`: every observable SSE event payload from the Agents
  API, with local capture time and elapsed milliseconds.
- `executor.log`: stdout/stderr from the isolated `codex exec-server` Docker
  process. Credentials are never written to this file.
- `target_probe.jsonl`: actual HTTP responses used to prove health, fault, and
  post-remediation state.
- `session.json`: the API's session creation response after field-aware
  redaction. It is ignored runtime output.
- `<turn>_events.jsonl`, `<turn>_final.md`, and `<turn>_items.json`: per-turn
  event slice, extracted model text, and retrieved session items. The item
  response is used to inspect tool results and errors instead of treating a
  completed turn event as sufficient proof.

The target service writes `service.jsonl`, `metrics.json`, and
`runtime_config.json` to the Docker named volume shared read-only with the
executor. The controller snapshots them to `artifacts/runtime/` and each run's
`runtime/` directory. These are generated evidence, not fixtures.

The controller redacts credential fields, authorization material, signed or
remote URLs, and secret-shaped values before JSONL persistence. It never logs
request authorization headers or environment variable values. The host
`OPENAI_API_KEY` and executor `OPENAI_EXECUTOR_API_KEY` are distinct; only the
latter is mapped to `CODEX_API_KEY` inside the executor process.
