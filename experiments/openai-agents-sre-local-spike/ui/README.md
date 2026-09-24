# ARMIE SRE Local Console

This is the browser presentation layer for the first local validation slice of
the ARMIE OpenAI Agents API architecture spike.

It is intentionally a thin Vite/React client. The browser talks only to the
local FastAPI controller on `127.0.0.1:8787`; it never receives credentials,
Docker access, arbitrary command capabilities, or a direct OpenAI connection.

## Run locally

From the repository root:

```bash
python3 -m venv .ui-venv
.ui-venv/bin/python -m pip install -r controller/requirements-ui.txt
npm --prefix experiments/openai-agents-sre-local-spike/ui install
```

In one terminal, start the controller:

```bash
.ui-venv/bin/python -m uvicorn controller.web_api:app --app-dir . --host 127.0.0.1 --port 8787
```

In another terminal, start Vite:

```bash
npm --prefix experiments/openai-agents-sre-local-spike/ui run dev -- --host 127.0.0.1 --port 5173
```

Open <http://127.0.0.1:5173> and click **Start local validation**. The target
is rebuilt from the deterministic fault fixture, real local probes run, and
the page updates through SSE. The proposal is controller-owned in this first
slice; approving it is optional and only recreates the synthetic target with
the known-safe configuration.

The **Customer Payment Surface** is a deliberately fixed, local-only payment
demo. Clicking **Simulate payment** sends one `ui-demo-order` checkout through
the FastAPI controller to the running target. A failure is shown first as a
customer-readable payment message, then as a technical-details dialog with
the observed HTTP status, error code, request ID, and dependency latency. It
does not accept card data and never performs a real charge.

## Build

```bash
npm --prefix experiments/openai-agents-sre-local-spike/ui run build
```
