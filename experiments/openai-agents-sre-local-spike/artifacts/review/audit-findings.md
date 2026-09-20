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
