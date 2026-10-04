import { useCallback, useEffect, useMemo, useState } from "react";

type JsonMap = Record<string, unknown>;

type TargetState = {
  base_url: string;
  health: JsonMap | null;
  metrics: JsonMap | null;
  downstream: JsonMap | null;
  timeline: JsonMap | null;
  last_checkout: JsonMap | null;
  incident_checkout: JsonMap | null;
  verification_checkout: JsonMap | null;
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

type LiveTurn = {
  label: string;
  status: string;
  final: string;
  event_count: number;
  event_types: Record<string, number>;
};

type LiveRun = {
  available: boolean;
  run_id: string;
  updated_at: string;
  status: string;
  message?: string;
  identity: JsonMap;
  target: {
    health: JsonMap | null;
    metrics: JsonMap | null;
    checkout_samples: number;
    checkout_statuses: unknown[];
    latest_checkout: JsonMap | null;
  };
  timeline?: JsonMap | null;
  session: {
    session_id: string | null;
    environment_id: string | null;
    connected: boolean;
    model: string | null;
  };
  turns: LiveTurn[];
  agent_event_type_counts: Record<string, number>;
  controller_timeline: { kind: string; captured_at: string }[];
  proposal: {
    text: string;
    mutation_executed: boolean;
    approval_recorded: boolean;
    verification_completed: boolean;
  };
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
    incident_checkout: null,
    verification_checkout: null,
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
  fault_ready: "Fault ready",
  approval_required: "Approval required",
  approval_denied: "Approval denied",
  remediation_running: "Applying remediation",
  verification_running: "Verifying recovery",
  verification_complete: "Recovery verified",
  verification_failed: "Verification failed",
  failed: "Run failed",
};

const eventTypes = [
  "ui.run.started",
  "ui.state.changed",
  "target.health.observed",
  "fault.reset",
  "executor.boundary.verified",
  "incident.reproduced",
  "contradictory.evidence.available",
  "local.validation.completed",
  "approval.required",
  "approval.recorded",
  "remediation.denied",
  "remediation.applied",
  "verification.completed",
  "remediation.failed",
  "payment.checkout.simulated",
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

function formatAmountCents(value: unknown): string {
  const amount = Number(value);
  return Number.isFinite(amount) ? `€${(amount / 100).toFixed(2)}` : "€10.99";
}

function formatTime(value: unknown): string {
  if (!value) return "—";
  const date = new Date(String(value));
  return Number.isNaN(date.valueOf()) ? String(value) : date.toLocaleTimeString();
}

function phaseClass(phase: string): string {
  if (phase === "verification_complete") return "success";
  if (phase === "failed" || phase === "verification_failed") return "danger";
  if (phase === "fault_ready" || phase === "approval_required" || phase === "remediation_running" || phase === "verification_running") return "warning";
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
  const [paymentDetailsOpen, setPaymentDetailsOpen] = useState(false);
  const [liveRun, setLiveRun] = useState<LiveRun | null>(null);
  const [liveRunVisible, setLiveRunVisible] = useState(true);

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
    try {
      const [logs, config] = await Promise.all([
        getJson<{ data: JsonMap[] }>("/api/evidence/logs?limit=80"),
        getJson<JsonMap>("/api/evidence/config"),
      ]);
      setEvidence({ logs: logs.data, config });
    } catch {
      // The target can be between container transitions; the next SSE/poll will retry.
    }
  }, []);

  const refreshEvents = useCallback(async () => {
    try {
      const result = await getJson<{ data: ConsoleEvent[] }>("/api/events");
      setEvents(result.data.slice(-100));
    } catch {
      // The EventSource reconnect path and the normal poll can recover later.
    }
  }, []);

  useEffect(() => {
    void refreshState();
    void refreshEvents();
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
    source.onopen = () => {
      setBackendError(null);
      void refreshEvents();
    };
    source.onerror = () => {
      setBackendError("SSE reconnecting — controller may be offline");
      void refreshEvents();
    };
    return () => {
      source.close();
    };
  }, [refreshEvents, refreshState]);

  useEffect(() => {
    void refreshEvidence();
    const timer = window.setInterval(() => {
      void refreshState();
      void refreshEvidence();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [refreshEvidence, refreshState]);

  const refreshLiveRun = useCallback(async () => {
    try {
      if (!liveRunVisible) return;
      const next = await getJson<LiveRun | { available: false }>("/api/live-run");
      setLiveRun(next.available ? next : null);
    } catch {
      // The observer is additive; the local console remains usable if it is unavailable.
    }
  }, [liveRunVisible]);

  useEffect(() => {
    void refreshLiveRun();
    const timer = window.setInterval(() => void refreshLiveRun(), 2000);
    return () => window.clearInterval(timer);
  }, [refreshLiveRun]);

  const runAction = async (action: () => Promise<unknown>, refreshLive = true) => {
    setBusy(true);
    setBackendError(null);
    try {
      await action();
      await refreshState();
      await refreshEvidence();
      if (refreshLive) await refreshLiveRun();
    } catch (error) {
      setBackendError(error instanceof Error ? error.message : "Controller request failed");
    } finally {
      setBusy(false);
    }
  };

  const runLocalAction = (path: string) => {
    setLiveRunVisible(false);
    setLiveRun(null);
    void runAction(() => postJson(path), false);
  };

  const startLiveInvestigation = () => {
    setLiveRunVisible(true);
    setLiveRun(null);
    void runAction(() => postJson("/api/live-run/start"));
  };

  const target = state.target;
  const checkoutResponse = target.last_checkout ?? {};
  const incidentCheckoutResponse = target.incident_checkout ?? {};
  const incidentCheckout = responseBody(incidentCheckoutResponse);
  const incidentCheckoutStatus = statusOf(incidentCheckoutResponse);
  const checkout = responseBody(checkoutResponse);
  const downstream = responseBody(target.downstream);
  const metrics = responseBody(target.metrics);
  const timeline = responseBody(target.timeline);
  const healthStatus = statusOf(target.health);
  const checkoutStatus = statusOf(checkoutResponse);
  const currentHealthBody = responseBody(target.health);
  const effectiveCheckoutResponse = checkoutResponse;
  const effectiveCheckout = responseBody(effectiveCheckoutResponse);
  const effectiveCheckoutStatus = checkoutStatus;
  const effectiveHealthStatus = healthStatus;
  const effectiveMetrics = metrics;
  const effectiveTimeline = timeline;
  const runtimeConfig = evidence.config?.runtime_config as JsonMap | undefined;
  const effectiveTimeoutBudget = runtimeConfig?.checkout_timeout_ms ?? effectiveTimeline.timeout_budget_ms;
  const checkoutFailed = effectiveCheckoutStatus !== "—" && effectiveCheckoutStatus !== "200";
  const verification = state.verification;
  const identity = state.identity;
  const effectiveIdentity = identity;
  const preIncident = typeof effectiveTimeline.pre_incident_observation === "object" && effectiveTimeline.pre_incident_observation !== null ? effectiveTimeline.pre_incident_observation as JsonMap : {};
  const incident = typeof effectiveTimeline.incident_observation === "object" && effectiveTimeline.incident_observation !== null ? effectiveTimeline.incident_observation as JsonMap : {};
  const timelineEvents: JsonMap[] = effectiveTimeline.pre_incident_observation ? [
    { event: "pre_incident_observation", timestamp: String(preIncident.window ?? "").split("/")[0], detail: `checkout HTTP ${stringOf(preIncident.checkout_status)} · downstream ${stringOf(preIncident.downstream_latency_ms)} ms` },
    { event: "deployment_loaded", timestamp: effectiveTimeline.deployment_loaded_at, detail: `timeout budget set to ${stringOf(effectiveTimeline.timeout_budget_ms)} ms` },
    { event: "incident_observation", timestamp: String(incident.window ?? "").split("/")[0], detail: `checkout HTTP ${stringOf(incident.checkout_status)} · dependency remained ${stringOf(incident.downstream_status)}` },
    { event: "contradictory_evidence", timestamp: "fresh observation", detail: stringOf(effectiveTimeline.observation) },
  ] : [];
  const timeoutRate = Number(effectiveMetrics.checkout_attempts) > 0 ? Math.round((Number(effectiveMetrics.checkout_timeouts ?? 0) / Number(effectiveMetrics.checkout_attempts)) * 100) : null;
  const latestEvents = useMemo(() => [...events].reverse(), [events]);
  const paymentAmount = formatAmountCents(checkout.amount_cents ?? 1099);
  const paymentDetail = {
    status: effectiveCheckoutStatus,
    error_code: effectiveCheckout.error_code,
    request_id: effectiveCheckout.request_id,
    downstream_latency_ms: effectiveCheckout.downstream_latency_ms,
    simulated_order: "ui-demo-order",
  };
  const liveStatus = liveRun?.status === "starting" ? "Preparing runtime" : liveRun?.status === "running" ? "Investigation in progress" : liveRun?.status === "approval_pending" ? "Approval required" : liveRun?.status === "remediation_running" ? "Applying approved change" : liveRun?.status === "verification_running" ? "Verifying recovery" : liveRun?.status === "completed" ? "Approved · verified" : liveRun?.status === "denied" ? "Approval denied" : liveRun?.status === "failed" ? "Run failed" : "Live run observed";
  const liveRunActive = Boolean(liveRun && !["completed", "denied", "failed"].includes(liveRun.status));
  const targetReadyForAgent = ["idle", "fault_ready"].includes(state.phase);
  const localTargetReady = !["idle", "target_starting", "remediation_running", "failed"].includes(state.phase);
  const canStartLiveInvestigation = !busy && !liveRunActive && targetReadyForAgent;
  const liveEventTypes = Object.entries(liveRun?.agent_event_type_counts ?? {}).slice(-8);
  const liveControllerEvents = [...(liveRun?.controller_timeline ?? [])].reverse();
  const sessionRunCheckoutStatus = liveRun?.target.latest_checkout ? stringOf(liveRun.target.latest_checkout.status) : "—";
  const sessionRunCheckoutFailed = sessionRunCheckoutStatus !== "—" && sessionRunCheckoutStatus !== "200";
  const compactId = (value: string | null) => value ? value.includes("…") ? value : `…${value.slice(-12)}` : "—";
  const observedServiceVersion = stringOf(currentHealthBody.version, stringOf(effectiveIdentity.target_service_version));
  const displayedPhase = state.phase;
  const displayedRunId = state.run_id;
  const historicalLiveRun = Boolean(liveRun && !liveRunActive);
  const agentStateLabel = liveRunActive
    ? (liveRun?.session.connected ? "connected" : "connecting")
    : historicalLiveRun
      ? "last run completed"
      : state.agent.status.split("_").join(" ");

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
          <strong>{liveRunActive ? "Live Agents API approval preview" : historicalLiveRun ? "Current target with retained Session evidence" : "Deterministic validation mode"}</strong>
          <span>{liveRunActive ? liveRun?.status === "starting" ? "The Controller is preparing the target, creating a real Session, and connecting the isolated executor." : liveRun?.status === "approval_pending" ? "The real Session has produced a proposal. Review the evidence below before approving or denying the bounded synthetic remediation." : "This view shows the active Session evidence and current controlled lifecycle state." : historicalLiveRun ? "Payment panels show the target now; the purple control room separately preserves the last completed real Session." : "This console is exercising the local target and controller boundary. No Agent API session is connected."}</span>
        </div>
        <span className={`provenance-chip ${liveRun ? "agent" : "controller"}`}>{liveRun ? "real session observed" : "controller-owned"}</span>
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
            <span className={`phase-pill ${phaseClass(displayedPhase)}`}><span className="dot" />{phaseLabels[displayedPhase] ?? displayedPhase}</span>
          </div>
          <div className="control-row">
            <button className="primary-button" disabled={busy || state.phase === "remediation_running" || liveRunActive} onClick={() => runLocalAction("/api/local/start")}>
              <span>▶</span> Start local validation
            </button>
            <button className="secondary-button" disabled={busy || liveRunActive} onClick={() => runLocalAction("/api/local/reset")}>
              Reset fault
            </button>
            <button className="ghost-button" disabled={busy || (state.phase === "idle" && !liveRun) || liveRunActive} onClick={() => runLocalAction("/api/local/stop")}>
              Stop target
            </button>
          </div>
          <div className="run-meta">
            <span>Run <code>{displayedRunId ?? "—"}</code></span>
            <span>Updated {formatTime(state.updated_at)}</span>
          </div>
        </div>
      </section>

      <section className="metric-grid incident-status-grid">
        <StatusPill label="Target health" value={effectiveHealthStatus === "200" ? "Healthy" : effectiveHealthStatus === "—" ? "Not observed" : `HTTP ${effectiveHealthStatus}`} tone={effectiveHealthStatus === "200" ? "success" : "neutral"} />
        <StatusPill label="Checkout" value={effectiveCheckoutStatus === "200" ? "Recovered" : checkoutFailed ? `HTTP ${effectiveCheckoutStatus}` : "Not observed"} tone={checkoutFailed ? "danger" : effectiveCheckoutStatus === "200" ? "success" : "neutral"} />
        <StatusPill label="Evidence boundary" value={state.phase === "idle" ? "Not checked" : "Read-only verified"} tone={state.phase !== "idle" ? "success" : "neutral"} />
        <StatusPill label="Approval" value={state.approval ? stringOf(state.approval.decision) : state.proposal ? "Required" : "Not required"} tone={state.approval?.approved ? "success" : state.proposal ? "warning" : "neutral"} />
      </section>

      <section className={`agent-control-room ${liveRun ? "has-live-run" : ""}`}>
        <div className="agent-card">
          <div className="agent-card-header">
            <div className="section-kicker">AGENTS API CONTROL ROOM</div>
            <span className="provenance-chip agent">purple boundary</span>
          </div>
          <div className="agent-status-row">
            <div className="agent-orbit"><span className="orbit-core">◎</span></div>
            <div>
              <h3>Agent API Session</h3>
              <div className="agent-state"><span className={`dot ${liveRun?.session.connected ? "" : "muted-dot"}`} />{agentStateLabel}</div>
            </div>
          </div>
          <p className="agent-message">{liveRunActive ? `Saved SRE Agent session is connected. ${liveStatus}. Investigation evidence is being observed from redacted artifacts.` : historicalLiveRun ? `The last real Saved-Agent Session is retained as review evidence (${liveStatus}). It is not the current target state.` : "The Controller will create the real Session and keep credentials outside the browser."}</p>
          <button className="agent-button" disabled={!canStartLiveInvestigation} onClick={startLiveInvestigation}>
            <span>◎</span> {liveRun?.status === "completed" ? "Start another investigation" : "Start Agents API investigation"}
          </button>
          <div className="agent-footnote"><span className="provenance-chip agent">{liveRunActive ? "live session evidence" : historicalLiveRun ? "retained session evidence" : "ready after fault reset"}</span><small>{targetReadyForAgent ? "Current target is ready for a real investigation." : "Reset the fault before starting a new Session."}</small></div>
        </div>

      {liveRun ? <section className="panel live-run-panel">
        <div className="panel-header"><div><div className="section-kicker">{historicalLiveRun ? "RETAINED AGENTS API RUN" : "LIVE AGENTS API RUN"}</div><h3>Investigation and approval from the real Session</h3></div><span className="provenance-chip agent">{liveStatus}</span></div>
        <p className="panel-description">The Workbench is reading sanitized runtime artifacts and controller state. It shows observable outputs, event metadata, and tool activity summaries—not hidden chain-of-thought. {historicalLiveRun ? `This completed run (${liveRun.run_id}) is retained evidence; the Payment API workspace below shows the target now.` : liveRun.status === "approval_pending" ? "Review the proposal and use the approval controls below." : liveRun.message || "The Controller is continuing the bounded workflow."}</p>
        <div className="live-run-meta">
          <div><span>Session</span><code>{compactId(liveRun.session.session_id)}</code></div>
          <div><span>Environment</span><code>{compactId(liveRun.session.environment_id)}</code></div>
          <div><span>Model</span><code>{stringOf(liveRun.session.model)}</code></div>
          <div><span>{historicalLiveRun ? "Connection event" : "Connection"}</span><strong className={liveRun.session.connected ? "live-good" : "live-warn"}>{liveRun.session.connected ? (historicalLiveRun ? "observed" : "connected") : "not observed"}</strong></div>
        </div>
        <div className="live-run-grid">
          <div>
            <div className="subsection-label">Observable investigation turns</div>
            <div className="live-turn-list">
              {liveRun.turns.map((turn) => <details className="live-turn" key={turn.label} open={turn.label === "remediation_proposal" || turn.label === "post_remediation_verification"}>
                <summary><strong>{turn.label.split("_").join(" ")}</strong><span>{turn.status} · {turn.event_count} events</span></summary>
                <CodeBlock value={turn.final || "No final output captured yet."} />
              </details>)}
            </div>
          </div>
          <div>
            <div className="subsection-label">Session-run target and safety state</div>
            <div className="live-facts">
              <div><span>Payment response</span><strong className={sessionRunCheckoutFailed ? "live-warn" : "live-good"}>{sessionRunCheckoutStatus === "—" ? "—" : `HTTP ${sessionRunCheckoutStatus}`}</strong></div>
              <div><span>Observed checkout samples</span><strong>{String(liveRun.target.checkout_samples)}</strong></div>
              <div><span>Mutation executed</span><strong className={liveRun.proposal.mutation_executed ? "live-warn" : "live-good"}>{liveRun.proposal.mutation_executed ? "yes" : "no"}</strong></div>
              <div><span>Approval recorded</span><strong>{liveRun.proposal.approval_recorded ? "yes" : "no"}</strong></div>
              <div><span>Same-session recheck</span><strong className={liveRun.proposal.verification_completed ? "live-good" : liveRun.status === "verification_running" ? "live-warn" : ""}>{liveRun.proposal.verification_completed ? "verified" : liveRun.status === "verification_running" ? "running" : "waiting"}</strong></div>
            </div>
            <div className="subsection-label event-label">Agent event types</div>
            <div className="event-chip-list">{liveEventTypes.map(([name, count]) => <span key={name}>{name} × {count}</span>)}</div>
          </div>
        </div>
        <div className="live-proposal">
          <div className="subsection-label">Evidence-backed proposed remediation</div>
          {liveRun.proposal.approval_recorded ? <div className={`live-decision-banner ${liveRun.proposal.verification_completed ? "verified" : "approved"}`}><strong>{liveRun.proposal.verification_completed ? "Approved · action executed · recovery verified" : "Approved · controlled action in progress"}</strong><span>{liveRun.proposal.verification_completed ? "The same Session inspected fresh post-remediation evidence." : "The Controller is continuing the allowlisted remediation path."}</span></div> : null}
          <CodeBlock value={liveRun.proposal.text || "Proposal not captured yet."} />
          <p className="live-approval-note">{liveRun.proposal.verification_completed ? "The allowlisted action was executed and the same Session completed a fresh recovery recheck. No terminal action was required." : liveRun.proposal.mutation_executed ? "The approved allowlisted action was executed. The Controller is now asking the same Session to perform a fresh recheck; no terminal action is required." : liveRun.status === "approval_pending" ? "No mutation has occurred. Review this proposal, its risks, verification, and rollback before deciding." : "The Controller is preserving the proposal and current lifecycle state."}</p>
          {liveRun.status === "approval_pending" && !liveRun.proposal.approval_recorded ? <><div className="approval-actions"><button className="danger-button" disabled={busy} onClick={() => void runAction(() => postJson("/api/live-run/approval", { decision: "deny" }))}>Deny live remediation</button><button className="approve-button" disabled={busy} onClick={() => void runAction(() => postJson("/api/live-run/approval", { decision: "approve" }))}>Approve live remediation</button></div><small className="approval-default">This decision resumes the same Session through the bounded Controller path. No arbitrary command or production target is exposed.</small></> : null}
        </div>
        <div className="agent-recovery">
          <div className="subsection-label">Same-session recovery verification</div>
          <div className="comparison"><div><span>Before</span><strong>{liveRun.target.checkout_statuses.length ? `HTTP ${String(liveRun.target.checkout_statuses[0])}` : "—"}</strong><small>observed incident response</small></div><div className="comparison-arrow">→</div><div><span>After</span><strong>{liveRun.proposal.mutation_executed && liveRun.target.checkout_statuses.length ? `HTTP ${String(liveRun.target.checkout_statuses[liveRun.target.checkout_statuses.length - 1])}` : "—"}</strong><small>{liveRun.proposal.verification_completed ? "verified by same-session Agent" : "awaiting approved remediation"}</small></div></div>
        </div>
        <div className="agent-trace-inline">
          <div className="panel-header"><div><div className="section-kicker">CONTROLLER EVENT STREAM</div><h3>Observable live operations</h3></div><span className="live-indicator"><span className="dot" /> SSE</span></div>
          <div className="event-list">
            {liveControllerEvents.length === 0 ? <div className="empty-state">Waiting for lifecycle events.</div> : liveControllerEvents.map((event, index) => <div className="event-row" key={`${event.kind}-${event.captured_at}-${index}`}><span className="event-number">{String(liveControllerEvents.length - index).padStart(2, "0")}</span><div><strong>{event.kind}</strong><small>{formatTime(event.captured_at)}</small></div></div>)}
          </div>
        </div>
      </section> : null}

      </section>

      <section className="incident-detail-region">
        <div className="region-header">
          <div>
            <div className="section-kicker">PAYMENT API WORKSPACE</div>
            <h3>Customer impact, service evidence, and recovery</h3>
          </div>
          <span className="provenance-chip observed">synthetic target</span>
        </div>
        <section className="content-grid">
        <div className="main-column">
          <section className={`panel payment-panel ${checkoutFailed ? "degraded" : checkoutStatus === "200" ? "recovered" : ""}`}>
            <div className="panel-header">
              <div><div className="section-kicker">CUSTOMER PAYMENT SURFACE</div><h3>What the customer experiences</h3></div>
              <span className="provenance-chip observed">synthetic local flow</span>
            </div>
            <div className="payment-layout">
              <div className="checkout-card">
                <div className="checkout-card-top"><span className="payment-brand">ARMIE <em>PAY</em></span><span className="lock-label">⌁ TEST ENVIRONMENT</span></div>
                <div className="checkout-title">Complete your payment</div>
                <div className="checkout-subtitle">Synthetic order · no real charge</div>
                <div className="checkout-order"><span>Order #UI-DEMO-1099</span><strong>{paymentAmount}</strong></div>
                <div className="payment-fields">
                  <div className="payment-field"><span>Card number</span><strong>••••  ••••  ••••  4242</strong></div>
                  <div className="payment-field"><span>Cardholder</span><strong>ARMIE TEST USER</strong></div>
                  <div className="payment-field small"><span>Expiry</span><strong>12 / 30</strong></div>
                  <div className="payment-field small"><span>Security code</span><strong>•••</strong></div>
                </div>
                <button className="payment-button" disabled={busy || (!localTargetReady && !liveRun) || liveRunActive} onClick={() => runLocalAction("/api/checkout/simulate")}>
                  {effectiveCheckoutStatus === "200" ? "Run payment again" : "Simulate payment"} · {paymentAmount}
                </button>
                <div className="checkout-secure">⌁ Routed only to the local synthetic payment API</div>
              </div>
              <div className="payment-explanation">
                <div className="section-kicker">BUSINESS SYMPTOM</div>
                {checkoutFailed ? <div className="payment-alert failure"><div className="payment-alert-icon">!</div><div><strong>Payment could not be completed</strong><p>The checkout service timed out while contacting its simulated payment dependency.</p></div></div> : effectiveCheckoutStatus === "200" ? <div className="payment-alert success"><div className="payment-alert-icon">✓</div><div><strong>Payment completed</strong><p>The latest synthetic checkout returned a successful response.</p></div></div> : <div className="payment-alert waiting"><div className="payment-alert-icon">…</div><div><strong>Payment surface is waiting</strong><p>Reset the fault or start local validation to exercise the customer-facing checkout flow.</p></div></div>}
                {checkoutFailed ? <div className="payment-technical"><div><span>Customer-visible result</span><strong>Payment failed</strong></div><div><span>Technical status</span><strong>HTTP {effectiveCheckoutStatus}</strong></div><div><span>Incident code</span><strong>{stringOf(effectiveCheckout.error_code)}</strong></div><button className="link-button" onClick={() => setPaymentDetailsOpen(true)}>View technical error details ↗</button></div> : null}
                {effectiveCheckoutStatus === "200" ? <div className="payment-technical"><div><span>Customer-visible result</span><strong>Payment confirmed</strong></div><div><span>Technical status</span><strong>HTTP 200</strong></div><div><span>Evidence</span><strong>new checkout response</strong></div></div> : null}
              </div>
            </div>
          </section>

          <section className="panel overview-panel">
            <div className="panel-header"><div><div className="section-kicker">SERVICE OBSERVABILITY</div><h3>What the target is telling us</h3></div><span className="provenance-chip observed">observed</span></div>
            <div className="metric-cards">
              <Metric label="Checkout status" value={effectiveCheckoutStatus === "—" ? "—" : `HTTP ${effectiveCheckoutStatus}`} detail={stringOf(effectiveCheckout.error_code, "No error code")} />
              <Metric label="Dependency latency" value={metrics.downstream_latency_ms ? `${stringOf(metrics.downstream_latency_ms)} ms` : downstream.observed_latency_ms ? `${stringOf(downstream.observed_latency_ms)} ms` : "—"} detail="synthetic downstream" />
              <Metric label="Timeout budget" value={effectiveTimeoutBudget ? `${stringOf(effectiveTimeoutBudget)} ms` : "—"} detail="runtime configuration" />
              <Metric label="Error rate" value={timeoutRate === null ? "—" : `${timeoutRate}%`} detail={`${stringOf(effectiveMetrics.checkout_timeouts, "—")} timed out`} />
            </div>
            <div className="fact-row">
              <span>Target <code>{target.base_url}</code></span>
              <span>Service <code>{observedServiceVersion}</code></span>
              <span>Deployment <code>{stringOf(effectiveIdentity.deployment_version)}</code></span>
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
              {tab === "timeline" ? <CodeBlock value={effectiveTimeline} /> : null}
              {state.phase === "idle" ? <div className="empty-state">No target evidence loaded yet.</div> : null}
            </div>
          </section>
        </div>

        {!liveRun ? <aside className="side-column">
          {!liveRun ? <section className="panel trace-panel">
            <div className="panel-header"><div><div className="section-kicker">EXECUTION TRACE</div><h3>Controller events</h3></div><span className="live-indicator"><span className="dot" /> SSE</span></div>
            <p className="panel-description">This stream is live controller telemetry. When the real Agent session is connected, Agent-returned items will appear here with separate provenance.</p>
            <div className="event-list">
              {latestEvents.length === 0 ? <div className="empty-state">Waiting for lifecycle events.</div> : latestEvents.map((event) => <div className="event-row" key={event.id}><span className="event-number">{String(event.id).padStart(2, "0")}</span><div><strong>{event.type}</strong><small>{formatTime(event.captured_at)}</small></div></div>)}
            </div>
          </section> : null}

          {!liveRun && state.proposal ? <section className="panel approval-panel attention">
            <div className="panel-header"><div><div className="section-kicker">CONTROLLED CHANGE</div><h3>Approval boundary</h3></div><span className="provenance-chip controller">controller</span></div>
            <>
              <div className="proposal-tag">PROPOSAL · {state.proposal.source}</div>
              <h4>{state.proposal.title}</h4>
              <p className="proposal-scope">Scope: {state.proposal.scope}</p>
              <div className="proposal-section"><span>Risks</span><ul>{state.proposal.risks.map((risk) => <li key={risk}>{risk}</li>)}</ul></div>
              <div className="proposal-section"><span>Verification plan</span><ol>{state.proposal.verification_plan.map((step) => <li key={step}>{step}</li>)}</ol></div>
              <div className="rollback"><span>Rollback</span><p>{state.proposal.rollback_plan}</p></div>
              {state.approval ? <div className={`decision-box ${state.approval.approved ? "approved" : "denied"}`}><strong>{state.approval.approved ? "Approved" : "Denied"}</strong><span>{state.approval.approved ? "Remediation is running or was applied." : "No remediation was executed."}</span></div> : <div className="approval-actions"><button className="danger-button" disabled={busy} onClick={() => void runAction(() => postJson("/api/approval", { decision: "deny", proposal_id: state.proposal!.id }), false)}>Deny</button><button className="approve-button" disabled={busy} onClick={() => void runAction(() => postJson("/api/approval", { decision: "approve", proposal_id: state.proposal!.id }), false)}>Approve remediation</button></div>}
              <small className="approval-default">Default: deny. No mutation occurs without an explicit approval request.</small>
            </>
          </section> : null}

          {!liveRun ? <section className="panel verification-panel">
            <div className="panel-header"><div><div className="section-kicker">RECOVERY</div><h3>Before / after</h3></div><span className="provenance-chip observed">new evidence</span></div>
            <div className="comparison"><div><span>Before</span><strong>{incidentCheckoutStatus === "—" ? "—" : `HTTP ${incidentCheckoutStatus}`}</strong><small>{stringOf(incidentCheckout.error_code, "Awaiting fault probe")}</small></div><div className="comparison-arrow">→</div><div><span>After</span><strong>{verification ? `HTTP ${statusOf(verification.checkout)}` : "—"}</strong><small>{verification?.verified ? "verified by new checkout" : "awaiting approved remediation"}</small></div></div>
            {state.error ? <div className="error-inline">{state.error}</div> : null}
          </section> : null}
        </aside> : null}
        </section>
      </section>

      {paymentDetailsOpen ? <div className="modal-backdrop" role="presentation" onClick={() => setPaymentDetailsOpen(false)}>
        <section className="details-modal" role="dialog" aria-modal="true" aria-labelledby="payment-error-title" onClick={(event) => event.stopPropagation()}>
          <div className="panel-header"><div><div className="section-kicker">TECHNICAL DETAIL</div><h3 id="payment-error-title">Payment failure evidence</h3></div><button className="close-button" aria-label="Close technical details" onClick={() => setPaymentDetailsOpen(false)}>×</button></div>
          <div className="modal-summary"><div className="modal-error-icon">!</div><div><strong>Customer payment failed</strong><p>The business symptom is backed by an observed response from the synthetic target.</p></div></div>
          <div className="detail-grid"><div><span>HTTP status</span><strong>{effectiveCheckoutStatus}</strong></div><div><span>Error code</span><strong>{stringOf(effectiveCheckout.error_code)}</strong></div><div><span>Request ID</span><strong>{stringOf(effectiveCheckout.request_id)}</strong></div><div><span>Dependency latency</span><strong>{stringOf(effectiveCheckout.downstream_latency_ms)} ms</strong></div></div>
          <CodeBlock value={paymentDetail} />
          <div className="modal-footnote"><span className="provenance-chip observed">observed target response</span><span>This is the bridge from customer impact to SRE evidence. Logs, metrics, and timeline remain in the console.</span></div>
        </section>
      </div> : null}

      <footer className="footer"><span>ARMIE SRE Local Console · experiment version {stringOf(identity.experiment_version)}</span><span>Commit <code>{stringOf(identity.git_commit, "unavailable")}</code></span></footer>
    </main>
  );
}
