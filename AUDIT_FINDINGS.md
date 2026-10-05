# Live Validation Audit Findings

Status: pre-fix audit recorded before implementation changes.

## Baseline

- The validation branch starts from `develop` at commit `80c4c43`.
- The existing implementation contained a saved-agent session payload and a self-hosted environment shape.
- Deterministic unit tests passed, but that did not establish Docker or live Agents API execution.

## Findings requiring correction

1. The controller used `OPENAI_API_KEY` as the executor `CODEX_API_KEY`. This violated credential separation and could place the host application credential in the executor environment.
2. The executor child environment was copied from the host environment and did not explicitly remove both OpenAI credential variables before setting `CODEX_API_KEY`.
3. The API client did not explicitly apply the configured OpenAI project header to requests.
4. Session metadata capture did not provide a safe, explicit record of the environment identifier and remote URL presence while avoiding persistence of the remote URL.
5. The controller did not retrieve session items after each turn, so event-stream completion alone was insufficient to prove tool results and errors were inspected.
6. Model text collection was not scoped cleanly to each turn, so first- and second-turn final responses could be mixed.
7. Redaction was pattern-based only and needed strengthening for credential field names, authorization material, signed URLs, and remote executor URLs.
8. The Compose startup path used volume deletion for reset. The live-validation path must not delete volumes without explicit authorization.
9. Approval behavior was guarded in the remediation function, but deterministic tests needed to prove empty and unexpected input deny and that the subprocess is not reached before approval.
10. The implementation must retain the saved-agent override payload without creating a replacement SRE agent definition.

## Runtime blockers observed before fixes

- Docker reports client and server version `29.8.0` on Docker Desktop `aarch64`, but `docker run --rm busybox:latest echo docker-ok` did not produce `docker-ok`; the container remained in `Created` state.
- The Docker API returned a timeout/error while inspecting the existing experiment target container.
- Repository file-content reads from the host `Documents` path hung independently of the Docker command; no unrelated repository mutation was attempted there.
