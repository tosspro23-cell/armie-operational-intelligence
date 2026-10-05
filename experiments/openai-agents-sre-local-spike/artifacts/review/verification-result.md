## Verification result — latest browser-triggered run

The bounded synthetic experiment is **recovering at the observed 168 ms
dependency latency**. The same Agents API Session independently checked the
service after the approved Controller action; it did not rely on the
Controller's success statement.

- **Health:** `GET /health` returned HTTP 200 with `status: ok`, version
  `synthetic-payment-api-2026.09.20.1`, and `checkout_path: ready`.
- **Checkout:** The verification probe returned HTTP 200 with
  `outcome: authorized`, `error_code: null`, and downstream latency of 168 ms.
  New structured logs record the restored configuration, gateway response, and
  `checkout_succeeded`.
- **Metrics:** The verification sample recorded **2 attempts, 2 successes, 0
  timeouts**. One success came from the controller probe and one from the
  Agent's independent probe.
- **Configuration and dependency:** The runtime configuration is in recovered
  mode with a **300 ms** timeout. The payment gateway remains `ok` at **168 ms**,
  above its 150 ms warning threshold.

## Remaining uncertainty

This verifies recovery for **two synthetic checkout attempts** and a short period
of ready health checks; it does not establish sustained recovery under load or
production-wide customer impact. Dependency latency remains elevated, and the
300 ms budget only provides headroom for the latency observed so far.

The recovered startup event reports service version `.1` alongside deployment
ID `deploy-2026-09-20.2`; that metadata ambiguity remains visible and should be
reconciled for a clean audit trail.

**Conclusion:** The synthetic checkout path is verified healthy at the current
observed dependency latency. The evidence does not yet demonstrate sustained
or production-wide recovery.
