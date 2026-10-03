# ARMIE SRE Local Console

This is the browser presentation layer for the first local validation slice of
the ARMIE OpenAI Agents API architecture spike.

It is intentionally a thin Vite/React client. The browser talks only to the
local FastAPI controller on `127.0.0.1:8787`; it never receives credentials,
Docker access, arbitrary command capabilities, or a direct OpenAI connection.
The Controller also exposes a bounded **Start Agents API investigation** action
that creates the real Session and owns the approval continuation. The browser
only receives sanitized state and observable event summaries.

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

Open <http://127.0.0.1:5173> and choose either mode:

- **Start local validation** rebuilds the deterministic fault fixture and
  demonstrates the local evidence and approval boundary without Agents API
  usage.
- **Start Agents API investigation** creates one real saved-agent Session,
  connects the Docker self-hosted executor, displays the observable
  investigation turns, and pauses for approval before the allowlisted
  remediation. The same Session then performs post-remediation verification.

The live action is available only when the Controller has the two local
credentials and the non-secret saved-agent/project identifiers. Approval is
explicit and defaults to no mutation.

Use **Reset fault** before a new run when the previous local run is still in an
approval or recovered state. Reset recreates the synthetic target with the
known fault and leaves it in `Fault ready`. The page is intentionally grouped
into two operational regions: the blue Incident/Payment API Workspace owns
the customer symptom and service evidence, while the purple Agents API Control
Room owns Session identity, investigation turns, approval, event stream,
controlled remediation, and same-session recovery verification.

Completed Session evidence remains visible in the purple region for review,
but it is labelled as retained evidence. The incident header and blue Payment
API Workspace use only the current Controller target state; resetting the fault
therefore shows the current HTTP 504 while preserving the prior HTTP 200 proof
inside the completed Session record.

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
