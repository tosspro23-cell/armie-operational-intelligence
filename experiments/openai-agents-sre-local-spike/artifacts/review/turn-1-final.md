## Initial investigation — latest browser-triggered run

The checkout failures are most consistent with a timeout budget that is too
short for the observed gateway latency. The active configuration is 120 ms,
the gateway responds in 168 ms, and the gateway remains `ok`. Health is 200
but marks checkout degraded. The available sample shows 9 attempts, 9
timeouts, and 0 successes.

The Agent inspected the runtime configuration, metrics, structured logs,
deployment metadata, downstream diagnostic, and runbook through the connected
self-hosted environment. The logs show successful 168 ms gateway responses
followed by `checkout_dependency_timeout`.

Competing explanations included gateway outage, gateway slowness, deployment
regression, and the too-short checkout timeout. Gateway outage is not
supported. A recent deployment remains plausible, but the direct mechanism is
the 120 ms budget being below 168 ms latency. The Agent recommended the
controller's fixed 300 ms restore, with explicit risks, verification, and
rollback considerations. No change was made in this turn.
