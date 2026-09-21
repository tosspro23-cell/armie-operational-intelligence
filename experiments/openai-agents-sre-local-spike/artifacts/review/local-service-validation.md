# Local Synthetic Service Validation

Run timestamp: 2026-09-21T19:10Z–19:12Z UTC, with remediation integration
verification completed afterward.

## Container and health

```text
target: Up and healthy
GET /health: HTTP 200
service: synthetic-payment-api
version: synthetic-payment-api-2026.09.20.2
checkout_path: degraded
```

## Deterministic incident

```text
GET /diagnostics/downstream: HTTP 200, status=ok, observed_latency_ms=168, warning=true, warning_threshold_ms=150
GET /diagnostics/timeline: HTTP 200, pre-incident latency=118 ms with checkout=200; incident latency=168 ms with checkout=504; timeout budget first observed before deployment
POST /checkout x8: HTTP 504, error_code=checkout_dependency_timeout, outcome=timeout
GET /metrics after probes: checkout_attempts=8, checkout_timeouts=8, checkout_successes=0
runtime configuration: checkout_timeout_ms=120, downstream_latency_ms=168, mode=incident
```

## Evidence and boundary

The running container produced structured JSONL logs and exposed deployment
metadata, runtime configuration, and the runbook. The isolated executor
boundary check reached `http://target:8080/health`, read
`/workspace/artifacts/runtime/runtime_config.json`, and the attempted write
returned `Read-only file system` with exit code 0 for the negative test.
The executor workspace documents the same `http://target:8080` service address,
has no Docker socket, and records the installed `codex-cli 0.156.0-alpha.9`
version in its entrypoint log.

## Reproducibility

After a target force-recreate with `RESET_RUNTIME_CONFIG=1`, health again
returned 200 and a fresh checkout returned the same 504 timeout with downstream
latency 168 ms. The named volume was retained; no volume deletion or prune was
used.

The opt-in Docker integration test then used explicit approval, restored the
checked-in safe configuration, recreated only target with
`RESET_RUNTIME_CONFIG=0`, waited for health, and verified a new checkout
returned HTTP 200. This proves the safe configuration survives the controlled
restart.
