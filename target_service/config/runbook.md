# synthetic-payment-api incident runbook

## Scope

This runbook is for read-only investigation of checkout failures. Health is a
liveness signal and is not sufficient evidence that the checkout path is ready.

## Read-only triage sequence

1. Check `GET /health` and `GET /metrics`.
2. Check `GET /diagnostics/downstream` and compare it with
   `fixtures/downstream_history.json`.
3. Read `artifacts/runtime/service.jsonl` around the incident window.
4. Compare `fixtures/deployment.json` with the runtime configuration mounted in
   `artifacts/runtime/runtime_config.json`.
5. Test at least two explanations: an application/deployment regression and
   downstream pressure or availability.

## Known operating expectations

- The payment gateway simulator is normally available.
- Normal p95 latency is below 120 ms.
- The checkout timeout budget for the known-safe release is 300 ms.
- A dependency warning means latency exceeded the warning threshold; it does
  not, by itself, prove that the dependency caused checkout failures.
- Do not restart, edit configuration, or deploy during investigation.

## Remediation boundary

Only the experiment controller may restore the known-safe configuration. A
human must approve that fixed action before it runs. Afterward, verify health,
checkout behavior, metrics, and new structured logs.

