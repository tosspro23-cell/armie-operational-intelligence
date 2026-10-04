## Post-remediation verification — latest browser-triggered run

After explicit Workbench approval, the Controller restored the checked-in 300 ms
configuration and restarted only the synthetic target. The same Agents API
Session independently verified the new state.

- Health: HTTP 200, checkout path `ready`.
- Checkout: HTTP 200, `authorized`, `error_code: null`, gateway latency 168 ms.
- Metrics: 2 attempts, 2 successes, 0 timeouts in the verification sample.
- Evidence: new logs show restored configuration, gateway response, and
  `checkout_succeeded`.

Recovery is verified for the bounded synthetic experiment. The sample is short,
gateway latency remains above its warning threshold, and this is not production
evidence.
