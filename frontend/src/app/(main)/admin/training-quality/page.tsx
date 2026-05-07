"use client";

import type { CSSProperties } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  adminApplyPromptOverride,
  adminGetTrainingQualityAnalysis,
  adminGetTrainingQualityGroups,
  adminListEvalRuns,
  adminListPromptOverrides,
  adminRollbackPromptOverride,
  adminStartEvalRun,
  getSession,
  type AnalyzerGroup,
  type AnalyzerPayload,
  type EvalRunSummary,
  type PromptOverride,
  type TrainingQualityGroup,
  type TrainingQualityGroups,
} from "../../../../lib/api";

const FRIENDLY_LABELS: Record<string, string> = {
  category_mismatch: "Category mismatch",
  priority_mismatch: "Priority mismatch",
  ticket_missing: "Ticket should have been created",
  ticket_created_mismatch: "Ticket created when it shouldn't",
  ticket_created: "Ticket-creation issue",
  response_tokens_missing: "Response missing required tokens (RAG)",
};

type FlowStage = "idle" | "applied" | "running" | "completed" | "failed";

function friendlyLabel(t: string) {
  return FRIENDLY_LABELS[t] ?? t;
}

function toPct(v: number | null | undefined, digits = 1) {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

function deltaValue(a: number | null | undefined, b: number | null | undefined) {
  if (a === null || a === undefined || b === null || b === undefined) return null;
  return b - a;
}

function deltaText(delta: number | null, digits = 1) {
  if (delta === null) return "—";
  return `${delta > 0 ? "+" : ""}${(delta * 100).toFixed(digits)}pp`;
}

export default function AdminTrainingQualityPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [data, setData] = useState<TrainingQualityGroups | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evalRuns, setEvalRuns] = useState<EvalRunSummary[]>([]);
  const [analyzer, setAnalyzer] = useState<AnalyzerPayload | null>(null);
  const [analyzerLoading, setAnalyzerLoading] = useState(false);
  const [analyzerStatus, setAnalyzerStatus] = useState("");
  const [overrides, setOverrides] = useState<PromptOverride[]>([]);
  const [overrideStatus, setOverrideStatus] = useState("");
  const [applyModal, setApplyModal] = useState<AnalyzerGroup | null>(null);
  const [lastAppliedOverrideId, setLastAppliedOverrideId] = useState<number | null>(null);
  const [lastEvalAfterRunId, setLastEvalAfterRunId] = useState<number | null>(null);
  const [flowStage, setFlowStage] = useState<FlowStage>("idle");
  const [flowMessage, setFlowMessage] = useState("");
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [showEvalHistory, setShowEvalHistory] = useState(false);
  const evalPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") {
          router.replace("/chat");
          return;
        }
        setReady(true);
        void Promise.all([loadGroups(), loadEvalRuns(), loadOverrides()]);
      })
      .catch(() => router.replace("/"));
    return () => {
      if (evalPollRef.current) clearInterval(evalPollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  async function loadGroups() {
    setLoading(true);
    setError(null);
    try {
      const res = await adminGetTrainingQualityGroups(5);
      setData(res);
    } catch (err) {
      setError((err as Error).message || "Failed to load grouped pending mismatches.");
    } finally {
      setLoading(false);
    }
  }

  async function loadEvalRuns() {
    try {
      const res = await adminListEvalRuns(20);
      setEvalRuns(res.runs);
      const running = res.runs.some((r) => r.status === "running");
      if (running && !evalPollRef.current) {
        evalPollRef.current = setInterval(() => void loadEvalRuns(), 5000);
      } else if (!running && evalPollRef.current) {
        clearInterval(evalPollRef.current);
        evalPollRef.current = null;
      }

      if (lastEvalAfterRunId) {
        const tracked = res.runs.find((r) => r.id === lastEvalAfterRunId);
        if (tracked?.status === "running") {
          setFlowStage("running");
          setFlowMessage(`Evaluation run #${lastEvalAfterRunId} is running...`);
        } else if (tracked?.status === "done") {
          setFlowStage("completed");
          setFlowMessage(`Evaluation run #${lastEvalAfterRunId} completed. Metrics updated below.`);
          void loadOverrides();
          setLastEvalAfterRunId(null);
        } else if (tracked?.status === "error") {
          setFlowStage("failed");
          setFlowMessage(`Evaluation run #${lastEvalAfterRunId} failed. Check eval history.`);
          setLastEvalAfterRunId(null);
        }
      }
    } catch {
      // keep stale view
    }
  }

  async function loadOverrides() {
    try {
      const res = await adminListPromptOverrides("active");
      setOverrides(res.overrides);
    } catch {
      // keep stale view
    }
  }

  async function runManualEval() {
    setOverrideStatus("Starting eval run...");
    try {
      const res = await adminStartEvalRun();
      setOverrideStatus(`Run #${res.run_id} started.`);
      void loadEvalRuns();
    } catch (err) {
      setOverrideStatus((err as Error).message || "Failed to start eval run.");
    }
  }

  async function loadAnalyzer() {
    setAnalyzerLoading(true);
    setAnalyzerStatus("");
    try {
      const res = await adminGetTrainingQualityAnalysis();
      setAnalyzer(res);
      setAnalyzerStatus(
        res.cached
          ? `Cached analysis from ${res.generated_at || "unknown time"}`
          : `Fresh analysis from ${res.model || "model"}`
      );
    } catch (err) {
      setAnalyzerStatus((err as Error).message || "Analyzer failed.");
    } finally {
      setAnalyzerLoading(false);
    }
  }

  async function handleApplyOverride(payload: {
    error_type: string;
    suggested_change: string;
    approved_change: string;
    affected_example_ids: number[];
    confidence: number;
    manually_edited: boolean;
  }) {
    setOverrideStatus("Applying override...");
    setFlowStage("idle");
    setFlowMessage("");
    try {
      const res = await adminApplyPromptOverride(payload);
      setApplyModal(null);
      setLastAppliedOverrideId(res.override.id);
      setFlowStage("applied");
      setFlowMessage(`Override #${res.override.id} applied.`);
      if (res.eval_after_run_id) {
        setLastEvalAfterRunId(res.eval_after_run_id);
        setFlowStage("running");
        setFlowMessage(
          `Override #${res.override.id} applied. Evaluation #${res.eval_after_run_id} started automatically.`
        );
      } else {
        setFlowMessage(
          `Override #${res.override.id} applied. No eval-after run started (another run may be active).`
        );
      }
      setOverrideStatus("");
      await Promise.all([loadOverrides(), loadEvalRuns()]);
    } catch (err) {
      setFlowStage("failed");
      setFlowMessage((err as Error).message || "Failed to apply override.");
      setOverrideStatus((err as Error).message || "Failed to apply override.");
    }
  }

  async function handleRollbackOverride(id: number) {
    setOverrideStatus("Rolling back...");
    try {
      await adminRollbackPromptOverride(id);
      setOverrideStatus(`Override #${id} rolled back.`);
      if (lastAppliedOverrideId === id) {
        setFlowStage("idle");
        setFlowMessage(`Override #${id} rolled back. You are back to the previous baseline behavior.`);
        setLastAppliedOverrideId(null);
      }
      await loadOverrides();
    } catch (err) {
      setOverrideStatus((err as Error).message || "Rollback failed.");
    }
  }

  const latestApplied = useMemo(() => {
    if (!overrides.length) return null;
    if (lastAppliedOverrideId) {
      return overrides.find((o) => o.id === lastAppliedOverrideId) ?? null;
    }
    return overrides[0] ?? null;
  }, [overrides, lastAppliedOverrideId]);

  if (!ready) return <div style={{ padding: "1.5rem" }}>Checking access...</div>;

  return (
    <div style={{ padding: "1.5rem", maxWidth: 1100, margin: "0 auto", display: "grid", gap: 14 }}>
      <header style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
        <h1 style={{ fontSize: "1.45rem", margin: 0 }}>Training Quality</h1>
        <span style={{ opacity: 0.72, fontSize: "0.9rem" }}>
          Guided flow: Pick suggestion → apply → auto-evaluate → keep or rollback
        </span>
      </header>

      <section style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <h2 style={h2Style}>1) Suggested fixes (first step)</h2>
          <button onClick={() => void loadAnalyzer()} disabled={analyzerLoading} style={btnStyle}>
            {analyzerLoading ? "Analyzing..." : analyzer ? "Re-analyze" : "Analyze pending"}
          </button>
        </div>
        <p style={subtleStyle}>One LLM call per analysis. Cached for 24h. Per-user limit: 1 request / 5 minutes.</p>
        {analyzerStatus && <p style={{ ...subtleStyle, marginTop: 6 }}>{analyzerStatus}</p>}
        <AnalyzerCards analyzer={analyzer} onApply={(g) => setApplyModal(g)} />
      </section>

      <section style={cardStyle}>
        <h2 style={h2Style}>2) Apply & evaluate status</h2>
        <FlowTimeline stage={flowStage} message={flowMessage} />
      </section>

      <section style={cardStyle}>
        <h2 style={h2Style}>3) Latest impact after change</h2>
        <LatestImpactCard override={latestApplied} />
      </section>

      <section style={cardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <h2 style={h2Style}>4) Active overrides</h2>
          <button onClick={() => void loadOverrides()} style={btnStyle}>Refresh</button>
        </div>
        {overrideStatus && <p style={subtleStyle}>{overrideStatus}</p>}
        <ActiveOverridesList overrides={overrides} onRollback={handleRollbackOverride} />
      </section>

      <section style={cardStyle}>
        <button onClick={() => setShowDiagnostics((s) => !s)} style={ghostBtnStyle}>
          {showDiagnostics ? "Hide diagnostics" : "Show diagnostics (mismatch groups)"}
        </button>
        {showDiagnostics && (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 10 }}>
              <h2 style={h2Style}>Mismatch groups</h2>
              <button onClick={() => void loadGroups()} disabled={loading} style={btnStyle}>
                {loading ? "Refreshing..." : "Refresh"}
              </button>
            </div>
            {error && <p style={{ color: "#c00", margin: "6px 0" }}>{error}</p>}
            {data && (
              <>
                <SummaryTiles data={data} />
                <div style={{ marginTop: 12, display: "grid", gap: 8 }}>
                  {data.groups.length === 0 ? (
                    <div style={softCardStyle}>No pending mismatches detected.</div>
                  ) : (
                    data.groups.map((g) => <GroupCard key={g.type} group={g} />)
                  )}
                </div>
              </>
            )}
          </>
        )}
      </section>

      <section style={cardStyle}>
        <button onClick={() => setShowEvalHistory((s) => !s)} style={ghostBtnStyle}>
          {showEvalHistory ? "Hide eval history" : "Show eval history"}
        </button>
        {showEvalHistory && (
          <EvalHistory runs={evalRuns} onRun={runManualEval} onRefresh={() => void loadEvalRuns()} />
        )}
      </section>

      {applyModal && (
        <ApplyOverrideModal
          group={applyModal}
          onClose={() => setApplyModal(null)}
          onSubmit={handleApplyOverride}
        />
      )}
    </div>
  );
}

function FlowTimeline({ stage, message }: { stage: FlowStage; message: string }) {
  const item = (label: string, active: boolean, done: boolean) => (
    <div
      style={{
        padding: "6px 10px",
        borderRadius: 999,
        border: "1px solid var(--border)",
        background: done ? "var(--chip-success-bg)" : active ? "var(--chip-info-bg)" : "var(--surface-muted)",
        color: done ? "var(--chip-success-text)" : active ? "var(--chip-info-text)" : "var(--muted)",
        fontSize: "0.82rem",
        fontWeight: 600,
      }}
    >
      {label}
    </div>
  );
  const appliedDone = stage === "running" || stage === "completed";
  const runningActive = stage === "running";
  const doneActive = stage === "completed";
  return (
    <div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {item("Applied", stage === "applied" || appliedDone, appliedDone)}
        {item("Eval running", runningActive, doneActive)}
        {item("Eval completed", doneActive, doneActive)}
      </div>
      <p style={{ ...subtleStyle, marginTop: 8 }}>
        {message || "Choose a suggestion and apply it to start automatic evaluation."}
      </p>
    </div>
  );
}

function LatestImpactCard({ override }: { override: PromptOverride | null }) {
  if (!override) {
    return <div style={softCardStyle}>No active override yet. Apply a suggested fix first.</div>;
  }
  const baseline = override.metrics?.baseline?.overall ?? override.baseline_accuracy;
  const after = override.metrics?.after?.overall ?? override.after_accuracy;
  const delta = deltaValue(baseline, after);
  const deltaColor = delta === null ? "var(--muted)" : delta > 0 ? "var(--chip-success-text)" : delta < 0 ? "var(--chip-danger-text)" : "var(--muted)";
  const pairs = [
    ["Overall", override.metrics?.baseline?.overall ?? override.baseline_accuracy, override.metrics?.after?.overall ?? override.after_accuracy],
    ["Category", override.metrics?.baseline?.category, override.metrics?.after?.category],
    ["Priority", override.metrics?.baseline?.priority, override.metrics?.after?.priority],
    ["Ticket", override.metrics?.baseline?.ticket_created, override.metrics?.after?.ticket_created],
    ["Response tokens", override.metrics?.baseline?.response_tokens, override.metrics?.after?.response_tokens],
  ] as const;

  return (
    <div style={softCardStyle}>
      <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap", marginBottom: 8 }}>
        <strong>Override #{override.id}</strong>
        <span style={subtleStyle}>{friendlyLabel(override.error_type)}</span>
        <span style={{ marginLeft: "auto", color: deltaColor, fontWeight: 700, fontSize: "1rem" }}>
          Δ {deltaText(delta)}
        </span>
      </div>
      <DataRow label="Overall" before={baseline} after={after} highlight />
      {pairs.slice(1).map(([label, b, a]) => (
        <DataRow key={label} label={label} before={b} after={a} />
      ))}
    </div>
  );
}

function DataRow({ label, before, after, highlight = false }: { label: string; before: number | null | undefined; after: number | null | undefined; highlight?: boolean }) {
  const d = deltaValue(before, after);
  const color = d === null ? "var(--muted)" : d > 0 ? "var(--chip-success-text)" : d < 0 ? "var(--chip-danger-text)" : "var(--muted)";
  return (
    <div style={{ display: "grid", gridTemplateColumns: "140px 1fr 1fr 1fr", gap: 8, fontSize: highlight ? "0.95rem" : "0.86rem", marginTop: 6 }}>
      <div style={{ fontWeight: highlight ? 700 : 600 }}>{label}</div>
      <div>Baseline: {toPct(before, 1)}</div>
      <div>After: {toPct(after, 1)}</div>
      <div style={{ color, fontWeight: 700 }}>Δ {deltaText(d, 1)}</div>
    </div>
  );
}

function AnalyzerCards({ analyzer, onApply }: { analyzer: AnalyzerPayload | null; onApply: (g: AnalyzerGroup) => void }) {
  if (!analyzer) return <div style={softCardStyle}>No analysis yet. Click “Analyze pending”.</div>;
  if (analyzer.groups.length === 0 && analyzer.rag_suggestions.length === 0) {
    return <div style={softCardStyle}>No suggestions returned.</div>;
  }
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {analyzer.groups.map((g, idx) => (
        <div key={`${g.type}-${idx}`} style={softCardStyle}>
          <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
            <strong>{friendlyLabel(g.type)}</strong>
            <span style={subtleStyle}>confidence {(g.confidence * 100).toFixed(0)}%</span>
            <span style={subtleStyle}>{g.affected_ids.length} examples</span>
          </div>
          <details style={{ marginTop: 6 }}>
            <summary style={{ cursor: "pointer", fontSize: "0.86rem" }}>Show suggestion text</summary>
            <pre style={preStyle}>{g.suggested_change}</pre>
            {!!g.rationale && <p style={subtleStyle}>Rationale: {g.rationale}</p>}
          </details>
          <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <button onClick={() => onApply(g)} style={primaryBtnStyle}>Apply and run evaluation</button>
            <span style={subtleStyle}>This appends the rule to the prompt and starts eval-after automatically.</span>
          </div>
        </div>
      ))}
      {analyzer.rag_suggestions.length > 0 && (
        <div style={{ ...softCardStyle, background: "var(--chip-warn-bg)", borderColor: "var(--chip-warn-border)" }}>
          <strong>RAG suggestions (not prompt fixes)</strong>
          {analyzer.rag_suggestions.map((r, idx) => (
            <div key={idx} style={{ marginTop: 4, fontSize: "0.86rem" }}>
              <strong>{r.type}:</strong> {r.description} <span style={subtleStyle}>({r.affected_ids.length} affected)</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ActiveOverridesList({ overrides, onRollback }: { overrides: PromptOverride[]; onRollback: (id: number) => void }) {
  if (!overrides.length) {
    return <div style={softCardStyle}>No active overrides. Apply one from Suggested fixes.</div>;
  }
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {overrides.map((o) => {
        const baseline = o.metrics?.baseline?.overall ?? o.baseline_accuracy;
        const after = o.metrics?.after?.overall ?? o.after_accuracy;
        const delta = deltaValue(baseline, after);
        const deltaColor = delta === null ? "var(--muted)" : delta > 0 ? "var(--chip-success-text)" : delta < 0 ? "var(--chip-danger-text)" : "var(--muted)";
        return (
          <div key={o.id} style={softCardStyle}>
            <div style={{ display: "flex", gap: 10, alignItems: "baseline", flexWrap: "wrap" }}>
              <strong>#{o.id}</strong>
              <span>{friendlyLabel(o.error_type)}</span>
              <span style={subtleStyle}>activated {o.activated_at || "—"}</span>
              <span style={{ marginLeft: "auto", color: deltaColor, fontWeight: 700 }}>Δ {deltaText(delta)}</span>
              <button onClick={() => onRollback(o.id)} style={btnStyle}>Rollback</button>
            </div>
            <details style={{ marginTop: 6 }}>
              <summary style={{ cursor: "pointer", fontSize: "0.85rem" }}>Show rule text</summary>
              <pre style={preStyle}>{o.approved_change}</pre>
            </details>
          </div>
        );
      })}
    </div>
  );
}

function EvalHistory({ runs, onRun, onRefresh }: { runs: EvalRunSummary[]; onRun: () => void; onRefresh: () => void }) {
  const running = runs.some((r) => r.status === "running");
  return (
    <div style={{ marginTop: 10 }}>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <button onClick={onRun} disabled={running} style={btnStyle}>{running ? "Running..." : "Run eval"}</button>
        <button onClick={onRefresh} style={btnStyle}>Refresh</button>
      </div>
      <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
        {runs.length === 0 ? (
          <div style={softCardStyle}>No eval runs yet.</div>
        ) : (
          runs.map((r) => (
            <div key={r.id} style={softCardStyle}>
              <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
                <strong>#{r.id}</strong>
                <span>{r.status}</span>
                <span>overall {toPct(r.accuracy_overall, 1)}</span>
                <span>passed {r.passed}/{r.total}</span>
                <span style={subtleStyle}>{r.started_at}</span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function SummaryTiles({ data }: { data: TrainingQualityGroups }) {
  const tiles = [{ label: "Total pending", value: data.total_pending }, ...data.groups.slice(0, 4).map((g) => ({ label: friendlyLabel(g.type), value: g.count }))];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 8 }}>
      {tiles.map((t) => (
        <div key={t.label} style={softCardStyle}>
          <div style={{ ...subtleStyle, margin: 0 }}>{t.label}</div>
          <div style={{ fontSize: "1.4rem", fontWeight: 700 }}>{t.value}</div>
        </div>
      ))}
    </div>
  );
}

function GroupCard({ group }: { group: TrainingQualityGroup }) {
  return (
    <div style={softCardStyle}>
      <div style={{ display: "flex", gap: 8, alignItems: "baseline", flexWrap: "wrap" }}>
        <strong>{friendlyLabel(group.type)}</strong>
        <span style={subtleStyle}>({group.count} examples)</span>
        {group.rag_signal && <span style={{ ...subtleStyle, color: "var(--chip-warn-text)" }}>RAG signal</span>}
      </div>
      <details style={{ marginTop: 6 }}>
        <summary style={{ cursor: "pointer", fontSize: "0.85rem" }}>Show preview examples</summary>
        <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
          {group.examples_preview.map((ex) => (
            <div key={ex.id} style={{ border: "1px solid var(--border)", borderRadius: 6, padding: 8, fontSize: "0.82rem" }}>
              <div>
                <code>#{ex.id}</code> <span style={subtleStyle}>[{ex.source_type}]</span> {ex.input_excerpt}
              </div>
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function ApplyOverrideModal({
  group,
  onClose,
  onSubmit,
}: {
  group: AnalyzerGroup;
  onClose: () => void;
  onSubmit: (payload: {
    error_type: string;
    suggested_change: string;
    approved_change: string;
    affected_example_ids: number[];
    confidence: number;
    manually_edited: boolean;
  }) => void;
}) {
  const [text, setText] = useState(group.suggested_change);
  const [submitting, setSubmitting] = useState(false);
  const edited = text !== group.suggested_change;
  return (
    <div style={modalBackdrop}>
      <div style={modalCard}>
        <h3 style={{ margin: "0 0 8px" }}>Apply and run evaluation</h3>
        <p style={subtleStyle}>
          {friendlyLabel(group.type)} · confidence {(group.confidence * 100).toFixed(0)}% · {group.affected_ids.length} affected examples
        </p>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={9}
          style={{ width: "100%", fontFamily: "monospace", fontSize: "0.9rem", border: "1px solid var(--border)", borderRadius: 8, padding: 10 }}
        />
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 12 }}>
          <button onClick={onClose} style={btnStyle}>Cancel</button>
          <button
            onClick={() => {
              setSubmitting(true);
              onSubmit({
                error_type: group.type,
                suggested_change: group.suggested_change,
                approved_change: text,
                affected_example_ids: group.affected_ids,
                confidence: group.confidence,
                manually_edited: edited,
              });
            }}
            disabled={submitting || !text.trim()}
            style={primaryBtnStyle}
          >
            {submitting ? "Applying..." : "Apply and run evaluation"}
          </button>
        </div>
      </div>
    </div>
  );
}

const cardStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 10,
  padding: "14px 16px",
  background: "var(--surface)",
};
const softCardStyle: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "10px 12px",
  background: "var(--surface-muted)",
};
const btnStyle: CSSProperties = {
  padding: "6px 12px",
  borderRadius: 8,
  border: "1px solid var(--border)",
  cursor: "pointer",
  background: "var(--surface)",
};
const ghostBtnStyle: CSSProperties = {
  ...btnStyle,
  fontSize: "0.88rem",
};
const primaryBtnStyle: CSSProperties = {
  ...btnStyle,
  background: "var(--color-action-accent)",
  borderColor: "var(--color-action-accent)",
  color: "white",
  fontWeight: 700,
};
const h2Style: CSSProperties = { margin: 0, fontSize: "1.03rem", fontWeight: 700 };
const subtleStyle: CSSProperties = { opacity: 0.75, fontSize: "0.84rem", margin: 0 };
const preStyle: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "10px 12px",
  whiteSpace: "pre-wrap",
  fontSize: "0.86rem",
  marginTop: 8,
};
const modalBackdrop: CSSProperties = {
  position: "fixed",
  inset: 0,
  background: "rgba(0,0,0,0.4)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 2000,
};
const modalCard: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 10,
  width: "min(700px, 92vw)",
  padding: 16,
};
