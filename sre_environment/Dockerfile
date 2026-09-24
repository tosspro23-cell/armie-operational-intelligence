FROM node:22-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl jq procps \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @openai/codex@alpha

# The spike intentionally follows the documented alpha channel, but records
# the concrete installed CLI version in every executor log for reproducibility.
RUN codex --version > /etc/codex-cli-version

COPY sre_environment/entrypoint.sh /usr/local/bin/sre-executor-entrypoint
COPY fixtures/deployment.json /opt/evidence/fixtures/deployment.json
COPY fixtures/downstream_history.json /opt/evidence/fixtures/downstream_history.json
COPY target_service/config/runbook.md /opt/evidence/runbook.md
COPY sre_environment/workspace/README.md /opt/evidence/workspace-guide.md
COPY fixtures/deployment.json /workspace/fixtures/deployment.json
COPY fixtures/downstream_history.json /workspace/fixtures/downstream_history.json
COPY target_service/config/runbook.md /workspace/runbook.md
COPY sre_environment/workspace/README.md /workspace/guide.md
RUN chmod 0755 /usr/local/bin/sre-executor-entrypoint

ENTRYPOINT ["/usr/local/bin/sre-executor-entrypoint"]
