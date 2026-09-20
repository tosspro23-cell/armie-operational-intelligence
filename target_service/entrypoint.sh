#!/bin/sh
set -eu

mkdir -p /app/shared
if [ ! -f /app/shared/runtime_config.json ]; then
  cp /app/default_runtime_config.json /app/shared/runtime_config.json
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8080

