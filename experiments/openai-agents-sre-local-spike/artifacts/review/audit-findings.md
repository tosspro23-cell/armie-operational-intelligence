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

Not demonstrated because credential readiness failed before session creation:

- real Agents API session creation;
- self-hosted environment connection;
- real agent shell/tool investigation;
- same-session contradictory-evidence reassessment;
- remediation recommendation and post-remediation verification.

Demonstrated after the Docker retry:

- target health and real HTTP checkout fault;
- structured evidence and deterministic fault reproducibility;
- executor target reachability, evidence read, and read-only write rejection.
