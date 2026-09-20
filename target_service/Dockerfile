FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY target_service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY target_service/app ./app
COPY fixtures/runtime_config_fault.json ./default_runtime_config.json
COPY fixtures/deployment.json ./metadata/deployment.json
COPY target_service/config/runbook.md ./runbook/runbook.md
COPY target_service/entrypoint.sh /usr/local/bin/target-entrypoint
RUN chmod 0755 /usr/local/bin/target-entrypoint

EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/target-entrypoint"]
