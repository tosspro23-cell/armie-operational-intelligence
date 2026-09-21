import { useCallback, useEffect, useMemo, useState } from "react";

type JsonMap = Record<string, unknown>;

type TargetState = {
  base_url: string;
  health: JsonMap | null;
  metrics: JsonMap | null;
  downstream: JsonMap | null;
  timeline: JsonMap | null;
  last_checkout: JsonMap | null;
};

type Proposal = {
  id: string;
  source: string;
  action_id: string;
  title: string;
  scope: string;
  risks: string[];
  verification_plan: string[];
  rollback_plan: string;
};

type ConsoleState = {
  mode: string;
  phase: string;
  run_id: string | null;
  started_at: string | null;
  updated_at: string;
  identity: JsonMap;
  target: TargetState;
  agent: {
    status: string;
    session_id: string | null;
    environment_id: string | null;
    message: string;
  };
  proposal: Proposal | null;
  approval: JsonMap | null;
  verification: JsonMap | null;
  error: string | null;
};

type ConsoleEvent = {
  id: number;
  type: string;
  captured_at: string;
  payload: JsonMap;
};

type Evidence = {
  logs: JsonMap[];
  config: JsonMap | null;
};

const initialState: ConsoleState = {
  mode: "local_deterministic",
  phase: "idle",
  run_id: null,
  started_at: null,
  updated_at: new Date().toISOString(),
  identity: {},
  target: {
    base_url: "http://127.0.0.1:18080",
    health: null,
    metrics: null,
    downstream: null,
    timeline: null,
    last_checkout: null,
  },
  agent: {
    status: "not_connected",
    session_id: null,
    environment_id: null,
    message: "Agent API is not connected in local deterministic mode.",
  },
  proposal: null,
  approval: null,
  verification: null,
  error: null,
};

const phaseLabels: Record<string, string> = {
  idle: "Idle",
  target_starting: "Starting target",
  approval_required: "Approval required",
  approval_denied: "Approval denied",
  remediation_running: "Applying remediation",
  verification_complete: "Recovery verified",
  verification_failed: "Verification failed",
  failed: "Run failed",
};

const eventTypes = [
  "ui.run.started",
  "ui.state.changed",
  "target.health.observed",
  "executor.boundary.verified",
  "incident.reproduced",
  "contradictory.evidence.available",
  "approval.required",
  "approval.recorded",
  "remediation.denied",
  "remediation.applied",
  "verification.completed",
  "remediation.failed",
  "ui.run.failed",
  "target.stopped",
];

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body?: JsonMap): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `${response.status} ${response.statusText}`);
  }
  return response.json() as Promise<T>;
}

function statusOf(value: unknown): string {
  if (typeof value === "object" && value !== null && "status" in value) {
    return String((value as JsonMap).status ?? "—");
  }
  return "—";
}

function stringOf(value: unknown, fallback = "—"): string {
  if (value === undefined || value === null || value === "") return fallback;
  return String(value);
}

function formatJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

function responseBody(value: JsonMap | null): JsonMap {
  const body = value?.body;
  return typeof body === "object" && body !== null ? (body as JsonMap) : {};
}

function formatTime(value: unknown): string {
  if (!value) return "—";
  const date = new Date(String(value));
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleTimeString();
}

function phaseClass(phase: string): string {
  if (phase === "verification_complete") return "success";
  if (phase === "failed" || phase === "verification_failed") return "danger";
  if (phase === "approval_required" || phase === "remediation_running") return "warning";
  return "neutral";
}

function StatusPill({ label, value, tone = "neutral" }: { label: string; value: string; tone?: string }) {
  return (
    <div className={`status-pill ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value}</strong>
      {detail ? <small>{detail}</small> : null}
    </div>
  );
}

function CodeBlock({ value }: { value: unknown }) {
  return <pre className="code-block">{typeof value === "string" ? value : formatJson(value)}</pre>;
}

export default function App() {
  const [state, setState] = useState<ConsoleState>(initialState);
  const [events, setEvents] = useState<ConsoleEvent[]>([]);
  const [evidence, setEvidence] = useState<Evidence>({ logs: [], config: null });
  const [tab, setTab] = useState("logs");
  const [busy, setBusy] = useState(false);
  const [backendError, setBackendError] = useState<string | null>(null);

  const refreshState = useCallback(async () => {
    try {
      const next = await getJson<ConsoleState>("/api/state");
      setState(next);
      setBackendError(null);
      return next;
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : "Backend unavailable");
      return null;
    }
  }, []);

  const refreshEvidence = useCallback(async () => {
    if (state.phase === "idle") return;
    try {
      const [logs, config] = await Promise.all([
        getJson<{ data: JsonMap[] }>("/api/evidence/logs?limit=80"),
        getJson<JsonMap>("/api/evidence/config"),
      ]);
      setEvidence({ logs: logs.data, config });
    } catch {
      // The target can be between container transitions; the next SSE/poll will retry.
    }
  }, [state.phase]);

  useEffect(() => {
    void refreshState();
    void getJson<{ data: ConsoleEvent[] }>("/api/events").then((result) => setEvents(result.data)).catch(() => undefined);
    const source = new EventSource("/api/events/stream");
    const handle = (message: MessageEvent<string>) => {
      try {
        const record = JSON.parse(message.data) as ConsoleEvent | { type: string; data: ConsoleState };
        if (record.type === "snapshot" && "data" in record) {
          setState(record.data);
          return;
        }
        if ("id" in record) {
          setEvents((current) => [...current.slice(-99), record]);
        }
        void refreshState();
      } catch {
        setBackendError("Received an unreadable event from the controller");
      }
    };
    for (const type of eventTypes) source.addEventListener(type, handle as EventListener);
    source.onerror = () => setBackendError("SSE reconnecting — controller may be offline");
    return () => {
      source.close();
    };
  }, [refreshState]);

  useEffect(() => {
    void refreshEvidence();
    const timer = window.setInterval(() => {
      void refreshState();
      void refreshEvidence();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refreshEvidence, refreshState]);

  const runAction = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setBackendError(null);
    try {
      await action();
      await refreshState();
      await refreshEvidence();
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : "Controller request failed");
    } finally {
      setBusy(false);
    }
  };

  const target = state.target;
  const checkoutResponse = target.last_checkout ?? {};
  const checkout = responseBody(checkoutResponse);
  const downstream = responseBody(target.downstream);
  const metrics = responseBody(target.metrics);
  const timeline = responseBody(target.timeline);
  const healthStatus = statusOf(target.health);
  const checkoutStatus = statusOf(checkoutResponse);
  const checkoutFailed = checkoutStatus !== "—" && checkoutStatus !== "200";
  const verification = state.verification;
  const identity = state.identity;
  const preIncident = typeof timeline.pre_incident_observation === "object" && timeline.pre_incident_observation !== null ? timeline.pre_incident_observation as JsonMap : {};
  const incident = typeof timeline.incident_observation === "object" && timeline.incident_observation !== null ? timeline.incident_observation as JsonMap : {};
  const timelineEvents: JsonMap[] = timeline.pre_incident_observation ? [
    { event: "pre_incident_observation", timestamp: String(preIncident.window ?? "").split("/")[0], detail: `checkout HTTP ${stringOf(preIncident.checkout_status)} · downstream ${stringOf(preIncident.downstream_latency_ms)} ms` },
    { event: "deployment_loaded", timestamp: timeline.deployment_loaded_at, detail: `timeout budget set to ${stringOf(timeline.timeout_budget_ms)} ms` },
    { event: "incident_observation", timestamp: String(incident.window ?? "").split("/")[0], detail: `checkout HTTP ${stringOf(incident.checkout_status)} · dependency remained ${stringOf(incident.downstream_status)}` },
    { event: "contradictory_evidence", timestamp: "fresh observation", detail: stringOf(timeline.observation) },
  ] : [];
  const timeoutRate = Number(metrics.checkout_attempts) > 0 ? Math.round((Number(metrics.checkout_timeouts ?? 0) / Number(metrics.checkout_attempts)) * 100) : null;
  const latestEvents = useMemo(() => [...events].reverse(), [events]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <div className="brand-mark">A</div>
          <div>
            <div className="eyebrow">ARMIE / OPERATIONAL INTELLIGENCE</div>
            <h1>SRE Local Console</h1>
          </div>
        </div>
        <div className="topbar-meta">
          <span className="local-badge"><span className="dot" /> LOCAL ONLY</span>
          <span className="muted">Architecture Spike #001</span>
        </div>
      </header>

      <section className="notice-bar">
        <div>
          <strong>Deterministic validation mode</strong>
          <span>This console is exercising the local target and controller boundary. No Agent API session is connected.</span>
        </div>
        <span className="provenance-chip controller">controller-owned</span>
      </section>

      {backendError ? <div className="error-banner"><strong>Controller notice</strong><span>{backendError}</span></div> : null}

      <section className="hero-grid">
        <div className="hero-card">
          <div className="section-kicker">INCIDENT WORKSPACE</div>
          <div className="hero-title-row">
            <div>
              <h2>Checkout degradation</h2>
              <p>synthetic-payment-api · deterministic fault fixture</p>
            </div>
            <span className={`phase-pill ${phaseClass(state.phase)}`}><span className="dot" />{phaseLabels[state.phase] ?? state.phase}</span>
          </div>
          <div className="control-row">
            <button className="primary-button" disabled={busy || state.phase === "remediation_running"} onClick={() => void runAction(() => postJson("/api/local/start"))}>
              <span>▶</span> Start local validation
            </button>
            <button className="secondary-button" disabled={busy} onClick={() => void runAction(() => postJson("/api/local/reset"))}>
              Reset fault
            </button>
            <button className="ghost-button" disabled={busy || state.phase === "idle"} onClick={() => void runAction(() => postJson("/api/local/stop"))}>
              Stop target
            </button>
          </div>
          <div className="run-meta">
            <span>Run <code>{state.run_id ?? "—"}</code></span>
            <span>Updated {formatTime(state.updated_at)}</span>
          </div>
        </div>
        <div className="agent-card">
          <div className="section-kicker">AGENT RUNTIME</div>
          <div className="agent-status-row">
            <div className="agent-orbit"><span className="orbit-core">◎</span></div>
            <div>
              <h3>Agent API</h3>
              <div className="agent-state"><span className="dot muted-dot" />{state.agent.status.split("_").join(" ")}</div>
            </div>
          </div>
          <p className="agent-message">{state.agent.message}</p>
          <div className="agent-footnote"><span className="provenance-chip agent">agent evidence reserved for live run</span></div>
        </div>
      </section>

      <section className="metric-grid">
        <StatusPill label="Target health" value={healthStatus === "200" ? "Healthy" : healthStatus === "—" ? "Not observed" : `HTTP ${healthStatus}`} tone={healthStatus === "200" ? "success" : "neutral"} />
        <StatusPill label="Checkout" value={checkoutStatus === "200" ? "Recovered" : checkoutFailed ? `HTTP ${checkoutStatus}` : "Not observed"} tone={checkoutFailed ? "danger" : checkoutStatus === "200" ? "success" : "neutral"} />
        <StatusPill label="Evidence boundary" value={state.phase === "idle" ? "Not checked" : "Read-only verified"} tone={state.phase === "idle" ? "neutral" : "success"} />
        <StatusPill label="Approval" value={state.approval ? stringOf(state.approval.decision) : state.proposal ? "Required" : "Not required"} tone={state.approval?.approved ? "success" : state.proposal ? "warning" : "neutral"} />
      </section>

      <section className="content-grid">
        <div className="main-column">
          <section className="panel overview-panel">
            <div className="panel-header"><div><div className="section-kicker">SERVICE OBSERVABILITY</div><h3>What the target is telling us</h3></div><span className="provenance-chip observed">observed</span></div>
            <div className="metric-cards">
              <Metric label="Checkout status" value={checkoutStatus === "—" ? "—" : `HTTP ${checkoutStatus}`} detail={stringOf(checkout.error_code, "No error code")} />
              <Metric label="Dependency latency" value={downstream.observed_latency_ms ? `${stringOf(downstream.observed_latency_ms)} ms` : "—"} detail="synthetic downstream" />
              <Metric label="Timeout budget" value={timeline.timeout_budget_ms ? `${stringOf(timeline.timeout_budget_ms)} ms` : "—"} detail="runtime configuration" />
              <Metric label="Error rate" value={timeoutRate === null ? "—" : `${timeoutRate}%`} detail={`${stringOf(metrics.checkout_timeouts, "—")} timed out`} />
            </div>
            <div className="fact-row">
              <span>Target <code>{target.base_url}</code></span>
              <span>Service <code>{stringOf(identity.target_service_version)}</code></span>
              <span>Deployment <code>{stringOf(identity.deployment_version)}</code></span>
            </div>
          </section>

          <section className="panel timeline-panel">
            <div className="panel-header"><div><div className="section-kicker">INCIDENT TIMELINE</div><h3>Evidence sequence</h3></div><span className="provenance-chip observed">observed / controller</span></div>
            <div className="timeline">
              {timelineEvents.length === 0 && state.phase === "idle" ? <div className="empty-state">Start local validation to populate the observed incident timeline.</div> : null}
              {timelineEvents.map((event, index) => (
                <div className="timeline-item" key={`${stringOf(event.timestamp, String(index))}-${index}`}>
                  <div className={`timeline-marker ${index === timelineEvents.length - 1 ? "current" : ""}`} />
                  <div className="timeline-copy"><div className="timeline-title"><strong>{stringOf(event.event, "event")}</strong><time>{formatTime(event.timestamp)}</time></div><p>{stringOf(event.detail, "Observed from target diagnostics")}</p></div>
                </div>
              ))}
              {state.approval ? <div className="timeline-item"><div className="timeline-marker current" /><div className="timeline-copy"><div className="timeline-title"><strong>Human approval recorded</strong><time>{formatTime(state.approval.recorded_at)}</time></div><p>{state.approval.approved ? "Approved allowlisted remediation." : "Denied; no mutation was executed."}</p></div></div> : null}
              {verification ? <div className="timeline-item"><div className="timeline-marker current" /><div className="timeline-copy"><div className="timeline-title"><strong>Post-change verification</strong><time>new evidence</time></div><p>{verification.verified ? "New checkout returned HTTP 200." : "Recovery verification did not pass."}</p></div></div> : null}
            </div>
          </section>

          <section className="panel evidence-panel">
            <div className="panel-header"><div><div className="section-kicker">EVIDENCE WORKSPACE</div><h3>Inspect the experiment artifacts</h3></div><span className="muted">read-only view</span></div>
            <div className="tabs">
              {["logs", "metrics", "config", "deployment", "runbook", "timeline"].map((item) => <button key={item} className={tab === item ? "tab active" : "tab"} onClick={() => setTab(item)}>{item}</button>)}
            </div>
            <div className="evidence-view">
              {tab === "logs" ? <CodeBlock value={evidence.logs} /> : null}
              {tab === "metrics" ? <CodeBlock value={metrics} /> : null}
              {tab === "config" ? <CodeBlock value={evidence.config && evidence.config.runtime_config} /> : null}
              {tab === "deployment" ? <CodeBlock value={evidence.config && evidence.config.deployment} /> : null}
              {tab === "runbook" ? <CodeBlock value={evidence.config && evidence.config.runbook} /> : null}
              {tab === "timeline" ? <CodeBlock value={timeline} /> : null}
              {state.phase === "idle" ? <div className="empty-state">No target evidence loaded yet.</div> : null}
            </div>
          </section>
        </div>

        <aside className="side-column">
          <section className="panel trace-panel">
            <div className="panel-header"><div><div className="section-kicker">EXECUTION TRACE</div><h3>Controller events</h3></div><span className="live-indicator"><span className="dot" /> SSE</span></div>
            <p className="panel-description">This stream is live controller telemetry. When the real Agent session is connected, Agent-returned items will appear here with separate provenance.</p>
            <div className="event-list">
              {latestEvents.length === 0 ? <div className="empty-state">Waiting for lifecycle events.</div> : latestEvents.map((event) => <div className="event-row" key={event.id}><span className="event-number">{String(event.id).padStart(2, "0")}</span><div><strong>{event.type}</strong><small>{formatTime(event.captured_at)}</small></div></div>)}
            </div>
          </section>

          <section className={`panel approval-panel ${state.proposal ? "attention" : ""}`}>
            <div className="panel-header"><div><div className="section-kicker">CONTROLLED CHANGE</div><h3>Approval boundary</h3></div><span className="provenance-chip controller">controller</span></div>
            {!state.proposal ? <div className="empty-state">The proposal will appear only after the deterministic incident has been reproduced.</div> : <>
              <div className="proposal-tag">PROPOSAL · {state.proposal.source}</div>
              <h4>{state.proposal.title}</h4>
              <p className="proposal-scope">Scope: {state.proposal.scope}</p>
              <div className="proposal-section"><span>Risks</span><ul>{state.proposal.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul></div>
              <div className="proposal-section"><span>Verification plan</span><ol>{state.proposal.verification_plan.map((step) => <li key={step}>{step}</li>)}</ol></div>
              <div className="rollback"><span>Rollback</span><p>{state.proposal.rollback_plan}</p></div>
              {state.approval ? <div className={`decision-box ${state.approval.approved ? "approved" : "denied"}`}><strong>{state.approval.approved ? "Approved" : "Denied"}</strong><span>{state.approval.approved ? "Remediation is running or was applied." : "No remediation was executed."}</span></div> : <div className="approval-actions"><button className="danger-button" disabled={busy} onClick={() => void runAction(() => postJson("/api/approval", { decision: "deny", proposal_id: state.proposal!.id }))}>Deny</button><button className="approve-button" disabled={busy} onClick={() => void runAction(() => postJson("/api/approval", { decision: "approve", proposal_id: state.proposal!.id }))}>Approve remediation</button></div>}
              <small className="approval-default">Default: deny. No mutation occurs without an explicit approval request.</small>
            </>}
          </section>

          <section className="panel verification-panel">
            <div className="panel-header"><div><div className="section-kicker">RECOVERY</div><h3>Before / after</h3></div><span className="provenance-chip observed">new evidence</span></div>
            <div className="comparison"><div><span>Before</span><strong>{checkoutStatus === "—" ? "—" : `HTTP ${checkoutStatus}`}</strong><small>{stringOf(checkout.error_code, "Awaiting fault probe")}</small></div><div className="comparison-arrow">→</div><div><span>After</span><strong>{verification ? `HTTP ${statusOf(verification.checkout)}` : "—"}</strong><small>{verification?.verified ? "verified by new checkout" : "awaiting approved remediation"}</small></div></div>
            {state.error ? <div className="error-inline">{state.error}</div> : null}
          </section>
        </aside>
      </section>

      <footer className="footer"><span>ARMIE SRE Local Console · experiment version {stringOf(identity.experiment_version)}</span><span>Commit <code>{stringOf(identity.git_commit, "unavailable")}</code></span></footer>
    </main>
  );
}
