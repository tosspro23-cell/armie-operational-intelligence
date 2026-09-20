# SRE executor workspace

This directory is intentionally read-only from the agent's perspective.

- `/workspace/artifacts/runtime/` contains live service logs, metrics, and the
  mounted runtime configuration.
- `/workspace/fixtures/deployment.json` contains deployment metadata.
- `/workspace/fixtures/downstream_history.json` contains public diagnostic
  history.
- `/workspace/runbook.md` is the read-only runbook.
- The target service is reachable at
  `http://synthetic-payment-api:8080` from this Docker network.

The executor container does not receive the Docker socket and cannot perform
the controller's remediation action.

