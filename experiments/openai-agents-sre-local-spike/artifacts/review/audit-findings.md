# Audit Findings Summary

The pre-fix audit is recorded in the tracked root `AUDIT_FINDINGS.md`.

Corrected before this validation attempt:

- separate application and executor credentials;
- explicit project header on Agents API requests;
- self-hosted stream-open and environment-connected lifecycle checks;
- per-turn events, final text, and session-items capture;
- field-aware redaction including remote URLs and authorization material;
- no volume deletion in Compose startup;
- deterministic denied-approval and executor-environment tests.

Corrected from the independent review in this validation attempt:

- approved remediation now clears `RESET_RUNTIME_CONFIG` before recreating only
  the target, with a real Docker integration test proving checkout recovery;
- final turn Markdown is extracted from the completed assistant Session Item
  and text artifacts are redacted before persistence;
- signed URLs embedded in free-form strings are scrubbed;
- the second-turn evidence is a fresh target timeline observation rather than
  a repeat of the downstream diagnostic;
- the executor workspace uses the Compose service name `target`;
- the executor records the installed Codex CLI version.

Demonstrated in live run `20261001T185830Z`:

- real Agents API session creation from the saved correct-project Agent;
- self-hosted environment connection using the returned environment identity;
- real Agent shell/tool investigation against mounted local evidence;
- same-session contradictory-evidence reassessment;
- evidence-backed remediation recommendation;
- explicit approval, controlled target-only remediation, and same-session
  post-remediation verification.

Repeated from the browser in live run `20261002T200149Z`, including an explicit
Workbench approval and the same-session post-remediation verification turn.

Revalidated read-only on 2026-10-03: the Agents API returned HTTP 200 for the
stored Session, its identity matched the retained run, its status was `idle`,
57 saved items were retrievable, and the Saved Agent identity/model matched.
No new Session or inference turn was created during this revalidation.

Demonstrated after the Docker retry:

- target health and real HTTP checkout fault;
- structured evidence and deterministic fault reproducibility;
- executor target reachability, evidence read, and read-only write rejection.
- Workbench approval actions are now exposed only for a live run in
  `approval_pending`; completed runs reject duplicate approval requests.

Latest browser-triggered completion `20261003T011902Z`:

- explicit Workbench approval was recorded before the allowlisted mutation;
- the Controller restored the known-safe 300 ms configuration and restarted
  only the synthetic target;
- the same Session completed a fresh verification turn with health 200,
  checkout 200, two successes, and zero timeouts;
- the latest run completed all four top-level turns with no failed or cancelled
  turn. The prior retained stream's post-completion `internal_error` remains
  disclosed as historical evidence rather than attributed to this run.
- final inspection found the latest one-off executor still running; it was
  stopped explicitly by exact container name, so end-to-end automatic cleanup
  remains an open operational limitation.
