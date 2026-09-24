#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ui_dir="$repo_root/experiments/openai-agents-sre-local-spike/ui"
venv_dir="${ARMIE_SRE_UI_VENV:-$repo_root/.ui-venv}"

if [[ ! -x "$venv_dir/bin/uvicorn" ]]; then
  echo "Missing UI Python environment: $venv_dir" >&2
  echo "Create it with: python3 -m venv .ui-venv && .ui-venv/bin/python -m pip install -r controller/requirements-ui.txt" >&2
  exit 1
fi

if [[ ! -d "$ui_dir/node_modules" ]]; then
  echo "Missing UI dependencies: $ui_dir/node_modules" >&2
  echo "Install them with: npm --prefix experiments/openai-agents-sre-local-spike/ui install" >&2
  exit 1
fi

backend_pid=""
frontend_pid=""
cleanup() {
  trap - TERM INT EXIT
  [[ -n "$backend_pid" ]] && kill "$backend_pid" 2>/dev/null || true
  [[ -n "$frontend_pid" ]] && kill "$frontend_pid" 2>/dev/null || true
}
trap cleanup TERM INT EXIT

"$venv_dir/bin/python" -m uvicorn controller.web_api:app \
  --app-dir "$repo_root" \
  --host 127.0.0.1 --port 8787 &
backend_pid=$!

npm --prefix "$ui_dir" run dev -- --host 127.0.0.1 --port 5173 &
frontend_pid=$!

echo "ARMIE SRE Local Console: http://127.0.0.1:5173"
echo "Controller API: http://127.0.0.1:8787"

# macOS ships Bash 3.2, which does not provide `wait -n`. Keep both
# processes alive portably and let the cleanup trap stop the sibling when one
# of them exits.
if (( BASH_VERSINFO[0] >= 5 )); then
  wait -n "$backend_pid" "$frontend_pid"
else
  while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
    sleep 1
  done
fi
