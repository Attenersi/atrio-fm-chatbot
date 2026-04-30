"use client";

import { useEffect, useRef, useState } from "react";
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

function friendlyLabel(t: string) {
  return FRIENDLY_LABELS[t] ?? t;
}

export default function AdminTrainingQualityPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [data, setData] = useState<TrainingQualityGroups | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evalRuns, setEvalRuns] = useState<EvalRunSummary[]>([]);
  const [evalStatus, setEvalStatus] = useState<string>("");
  const evalPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [analyzer, setAnalyzer] = useState<AnalyzerPayload | null>(null);
  const [analyzerLoading, setAnalyzerLoading] = useState(false);
  const [analyzerStatus, setAnalyzerStatus] = useState<string>("");
  const [overrides, setOverrides] = useState<PromptOverride[]>([]);
  const [overrideStatus, setOverrideStatus] = useState<string>("");
  const [applyModal, setApplyModal] = useState<AnalyzerGroup | null>(null);

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") {
          router.replace("/chat");
          return;
        }
        setReady(true);
        void load();
        void loadEvalRuns();
        void loadOverrides();
      })
      .catch(() => router.replace("/"));
    return () => {
      if (evalPollRef.current) clearInterval(evalPollRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const res = await adminGetTrainingQualityGroups(5);
      setData(res);
    } catch (err) {
      setError((err as Error).message || "Load failed");
    } finally {
      setLoading(false);
    }
  }

  async function loadEvalRuns() {
    try {
      const res = await adminListEvalRuns(10);
      setEvalRuns(res.runs);
      const running = res.runs.some((r) => r.status === "running");
      if (running && !evalPollRef.current) {
        evalPollRef.current = setInterval(() => void loadEvalRuns(), 5000);
      } else if (!running && evalPollRef.current) {
        clearInterval(evalPollRef.current);
        evalPollRef.current = null;
      }
    } catch (err) {
      // ignore; user will see stale list and can refresh
    }
  }

  async function handleRunEval() {
    setEvalStatus("Starting...");
    try {
      const res = await adminStartEvalRun();
      setEvalStatus(`Started run #${res.run_id}. Polling for completion...`);
      void loadEvalRuns();
    } catch (err) {
      const m = (err as Error).message || String(err);
      setEvalStatus(m);
    }
  }

  async function loadOverrides() {
    try {
      const res = await adminListPromptOverrides("active");
      setOverrides(res.overrides);
    } catch {
      // ignore; user can refresh
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
    setOverrideStatus("Applying...");
    try {
      const res = await adminApplyPromptOverride(payload);
      const baseline = res.baseline.accuracy_overall;
      const baselineStr =
        baseline !== null && baseline !== undefined
          ? `${(baseline * 100).toFixed(1)}%`
          : "n/a";
      setOverrideStatus(
        `Override #${res.override.id} applied. Baseline ${baselineStr}.` +
          (res.eval_after_run_id ? ` Eval after #${res.eval_after_run_id} starting...` : ""),
      );
      setApplyModal(null);
      void loadOverrides();
      void loadEvalRuns();
    } catch (err) {
      setOverrideStatus((err as Error).message || "Apply failed");
    }
  }

  async function handleRollbackOverride(overrideId: number) {
    setOverrideStatus("Rolling back...");
    try {
      await adminRollbackPromptOverride(overrideId);
      setOverrideStatus(`Override #${overrideId} rolled back.`);
      void loadOverrides();
    } catch (err) {
      setOverrideStatus((err as Error).message || "Rollback failed");
    }
  }

  async function loadAnalyzer() {
    setAnalyzerLoading(true);
    setAnalyzerStatus("");
    try {
      const res = await adminGetTrainingQualityAnalysis();
      setAnalyzer(res);
      if (res.cached) {
        setAnalyzerStatus(`Cached, generated ${res.generated_at}`);
      } else {
        setAnalyzerStatus(`Fresh analysis from ${res.model || "model"}`);
      }
    } catch (err) {
      setAnalyzerStatus((err as Error).message || "Analyzer failed");
    } finally {
      setAnalyzerLoading(false);
    }
  }

  if (!ready) {
    return <div style={{ padding: "1.5rem" }}>Checking access...</div>;
  }

  return (
    <div style={{ padding: "1.5rem", maxWidth: 1100, margin: "0 auto" }}>
      <header style={{ display: "flex", alignItems: "baseline", gap: 16, marginBottom: 16 }}>
        <h1 style={{ fontSize: "1.5rem", fontWeight: 600, margin: 0 }}>Training Quality</h1>
        <span style={{ opacity: 0.7, fontSize: "0.9rem" }}>
          Pending training_examples grouped by mismatch type. No LLM calls; pure aggregation.
        </span>
        <button onClick={() => void load()} disabled={loading} style={btnStyle}>
          {loading ? "Refreshing..." : "Refresh"}
        </button>
      </header>

      {error && (
        <div style={{ ...cardStyle, borderColor: "#c00", color: "#c00" }}>Error: {error}</div>
      )}

      <ActiveOverridesSection
        overrides={overrides}
        status={overrideStatus}
        onRollback={handleRollbackOverride}
        onRefresh={() => void loadOverrides()}
      />

      {data && (
        <>
          <SummaryTiles data={data} />
          <div style={{ marginTop: 16, display: "grid", gap: 12 }}>
            {data.groups.length === 0 && (
              <div style={cardStyle}>No pending mismatches detected.</div>
            )}
            {data.groups.map((g) => (
              <GroupCard key={g.type} group={g} />
            ))}
          </div>
          <p style={{ opacity: 0.6, fontSize: "0.8rem", marginTop: 16 }}>
            Note: a single example with multiple errors (e.g. category + ticket) counts in every
            applicable group, so the sum of group counts can exceed total_pending.
            <br />
            Generated at: {data.generated_at}
          </p>

          <EvalSection
            runs={evalRuns}
            evalStatus={evalStatus}
            onRun={handleRunEval}
            onRefresh={() => void loadEvalRuns()}
          />

          <AnalyzerSection
            analyzer={analyzer}
            loading={analyzerLoading}
            status={analyzerStatus}
            onLoad={() => void loadAnalyzer()}
            onApply={(group) => setApplyModal(group)}
          />
        </>
      )}

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

function ActiveOverridesSection({
  overrides,
  status,
  onRollback,
  onRefresh,
}: {
  overrides: PromptOverride[];
  status: string;
  onRollback: (id: number) => void;
  onRefresh: () => void;
}) {
  return (
    <div style={{ marginTop: 12, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 600 }}>Active prompt overrides</h2>
        <span style={{ opacity: 0.7, fontSize: "0.85rem" }}>
          Each rule is appended to the end of SYSTEM_PROMPT at chat time.
        </span>
        <button onClick={onRefresh} style={btnStyle}>Refresh</button>
      </div>
      {status && <div style={{ fontSize: "0.85rem", opacity: 0.85, marginBottom: 6 }}>{status}</div>}
      {overrides.length === 0 ? (
        <div style={{ ...cardStyle, opacity: 0.8 }}>No active overrides. Apply one from the Suggested fixes section below.</div>
      ) : (
        <div style={{ display: "grid", gap: 8 }}>
          {overrides.map((o) => {
            const baseline = o.baseline_accuracy;
            const after = o.after_accuracy;
            const delta = baseline !== null && after !== null && baseline !== undefined && after !== undefined
              ? after - baseline
              : null;
            const deltaColor = delta === null ? "inherit" : delta > 0 ? "#0a7d2c" : delta < 0 ? "#c00" : "#666";
            return (
              <div key={o.id} style={cardStyle}>
                <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
                  <strong>#{o.id}</strong>
                  <span>{o.error_type}</span>
                  <span style={{ opacity: 0.7 }}>activated {o.activated_at}</span>
                  <button onClick={() => onRollback(o.id)} style={{ ...btnStyle, marginLeft: "auto" }}>
                    Rollback
                  </button>
                </div>
                <pre style={{
                  background: "rgba(0,0,0,0.05)", padding: "10px 12px", borderRadius: 6,
                  whiteSpace: "pre-wrap", fontSize: "0.9rem", marginTop: 8,
                }}>{o.approved_change}</pre>
                <div style={{ fontSize: "0.85rem", opacity: 0.85 }}>
                  Baseline: {baseline !== null && baseline !== undefined ? `${(baseline * 100).toFixed(1)}%` : "—"}
                  {" "}
                  After: {after !== null && after !== undefined ? `${(after * 100).toFixed(1)}%` : "pending"}
                  {delta !== null && (
                    <>
                      {" "}
                      <span style={{ color: deltaColor, fontWeight: 600 }}>
                        Δ {delta > 0 ? "+" : ""}{(delta * 100).toFixed(1)}pp
                      </span>
                    </>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
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
    <div style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.4)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000,
    }}>
      <div style={{ background: "white", padding: 20, borderRadius: 8, width: "min(640px, 92vw)" }}>
        <h3 style={{ margin: 0, marginBottom: 6 }}>Apply override: {group.type}</h3>
        <div style={{ fontSize: "0.85rem", opacity: 0.7, marginBottom: 10 }}>
          Confidence {(group.confidence * 100).toFixed(0)}%, {group.affected_ids.length} affected examples.
          The text below will be appended to SYSTEM_PROMPT verbatim.
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
          style={{ width: "100%", fontFamily: "monospace", fontSize: "0.9rem", padding: 10 }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 12, justifyContent: "flex-end" }}>
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
            style={{ ...btnStyle, background: "#1d6f42", color: "white", borderColor: "#1d6f42" }}
          >
            {submitting ? "Applying..." : "Apply"}
          </button>
        </div>
      </div>
    </div>
  );
}

function EvalSection({
  runs,
  evalStatus,
  onRun,
  onRefresh,
}: {
  runs: EvalRunSummary[];
  evalStatus: string;
  onRun: () => void;
  onRefresh: () => void;
}) {
  const running = runs.some((r) => r.status === "running");
  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 600 }}>Golden eval history</h2>
        <span style={{ opacity: 0.7, fontSize: "0.85rem" }}>
          Runs the locked-in golden snapshot through the live RAG + LLM pipeline.
          Takes ~3–5 min for 80 cases (NVIDIA RPM-throttled).
        </span>
        <button onClick={onRun} disabled={running} style={btnStyle}>
          {running ? "Running..." : "Run eval"}
        </button>
        <button onClick={onRefresh} style={btnStyle}>Refresh</button>
      </div>
      {evalStatus && <div style={{ fontSize: "0.85rem", opacity: 0.85 }}>{evalStatus}</div>}
      <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
        {runs.length === 0 && <div style={cardStyle}>No eval runs yet. Click Run eval to baseline.</div>}
        {runs.map((r) => (
          <div key={r.id} style={cardStyle}>
            <div style={{ display: "flex", gap: 12, alignItems: "baseline", flexWrap: "wrap" }}>
              <strong>#{r.id}</strong>
              <span>{r.status}</span>
              <span>passed {r.passed}/{r.total}</span>
              {r.accuracy_overall !== null && (
                <span>overall {(r.accuracy_overall * 100).toFixed(1)}%</span>
              )}
              {r.accuracy_category !== null && (
                <span>category {(r.accuracy_category * 100).toFixed(0)}%</span>
              )}
              {r.accuracy_priority !== null && (
                <span>priority {(r.accuracy_priority * 100).toFixed(0)}%</span>
              )}
              {r.accuracy_ticket_created !== null && (
                <span>ticket {(r.accuracy_ticket_created * 100).toFixed(0)}%</span>
              )}
              <span style={{ opacity: 0.6 }}>{r.started_at}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function SummaryTiles({ data }: { data: TrainingQualityGroups }) {
  const tiles = [
    { label: "Total pending", value: data.total_pending },
    ...data.groups.slice(0, 4).map((g) => ({
      label: friendlyLabel(g.type),
      value: g.count,
    })),
  ];
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 12 }}>
      {tiles.map((t) => (
        <div key={t.label} style={{ ...cardStyle, padding: "12px 16px" }}>
          <div style={{ opacity: 0.7, fontSize: "0.8rem" }}>{t.label}</div>
          <div style={{ fontSize: "1.6rem", fontWeight: 600 }}>{t.value}</div>
        </div>
      ))}
    </div>
  );
}

function GroupCard({ group }: { group: TrainingQualityGroup }) {
  return (
    <div style={cardStyle}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: "1.05rem", fontWeight: 600 }}>
          {friendlyLabel(group.type)}
        </h2>
        <span style={{ opacity: 0.7 }}>({group.count} examples)</span>
        {group.rag_signal && (
          <span style={{
            background: "#fff3cd", color: "#664d03", border: "1px solid #ffe69c",
            fontSize: "0.75rem", padding: "2px 8px", borderRadius: 12,
          }}>
            RAG signal — likely retrieval issue, not prompt
          </span>
        )}
      </div>
      <details>
        <summary style={{ cursor: "pointer", opacity: 0.85 }}>
          Show {Math.min(group.examples_preview.length, 5)} preview examples
        </summary>
        <div style={{ marginTop: 8, display: "grid", gap: 6 }}>
          {group.examples_preview.map((ex) => (
            <div key={ex.id} style={{
              background: "rgba(0,0,0,0.03)", padding: "8px 10px", borderRadius: 6,
              fontSize: "0.85rem",
            }}>
              <code>#{ex.id}</code> <span style={{ opacity: 0.8 }}>[{ex.source_type}]</span>{" "}
              {ex.input_excerpt}
              {Object.keys(ex.expected || {}).length > 0 && (
                <div style={{ marginTop: 4, opacity: 0.85 }}>
                  expected: <code>{JSON.stringify(ex.expected)}</code>
                  {Object.keys(ex.actual || {}).length > 0 && (
                    <>
                      {" "}actual: <code>{JSON.stringify(ex.actual)}</code>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      </details>
    </div>
  );
}

function AnalyzerSection({
  analyzer,
  loading,
  status,
  onLoad,
  onApply,
}: {
  analyzer: AnalyzerPayload | null;
  loading: boolean;
  status: string;
  onLoad: () => void;
  onApply: (group: AnalyzerGroup) => void;
}) {
  return (
    <div style={{ marginTop: 24 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 8 }}>
        <h2 style={{ margin: 0, fontSize: "1.15rem", fontWeight: 600 }}>Suggested fixes (LLM)</h2>
        <span style={{ opacity: 0.7, fontSize: "0.85rem" }}>
          1 LLM call per analysis. Cached for 24h. Per-user limit 1/5min.
        </span>
        <button onClick={onLoad} disabled={loading} style={btnStyle}>
          {loading ? "Analyzing..." : analyzer ? "Re-analyze" : "Analyze pending"}
        </button>
      </div>
      {status && (
        <div style={{ fontSize: "0.85rem", opacity: 0.85, marginBottom: 8 }}>
          {analyzer?.cached && (
            <span style={{
              background: "#d1ecf1", color: "#0c5460", border: "1px solid #bee5eb",
              fontSize: "0.75rem", padding: "2px 8px", borderRadius: 12, marginRight: 8,
            }}>
              cache hit
            </span>
          )}
          {status}
        </div>
      )}
      {analyzer && (
        <div style={{ display: "grid", gap: 8 }}>
          {analyzer.groups.length === 0 && analyzer.rag_suggestions.length === 0 && (
            <div style={cardStyle}>No suggestions returned.</div>
          )}
          {analyzer.groups.map((g, idx) => (
            <div key={`${g.type}-${idx}`} style={cardStyle}>
              <div style={{ display: "flex", gap: 12, alignItems: "baseline" }}>
                <strong>{g.type}</strong>
                <span style={{ opacity: 0.7 }}>confidence {(g.confidence * 100).toFixed(0)}%</span>
                <span style={{ opacity: 0.7 }}>{g.affected_ids.length} examples</span>
              </div>
              <pre style={{
                background: "rgba(0,0,0,0.05)", padding: "10px 12px", borderRadius: 6,
                whiteSpace: "pre-wrap", fontSize: "0.9rem", marginTop: 8,
              }}>{g.suggested_change}</pre>
              {g.rationale && (
                <div style={{ fontSize: "0.85rem", opacity: 0.8 }}>
                  Rationale: {g.rationale}
                </div>
              )}
              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button onClick={() => onApply(g)} style={{ ...btnStyle, background: "#1d6f42", color: "white", borderColor: "#1d6f42" }}>
                  Approve / Edit
                </button>
                <span style={{ opacity: 0.6, fontSize: "0.8rem", alignSelf: "center" }}>
                  Will append the rule to SYSTEM_PROMPT and start an eval-after run.
                </span>
              </div>
            </div>
          ))}
          {analyzer.rag_suggestions.length > 0 && (
            <div style={{ ...cardStyle, background: "rgba(255,243,205,0.5)", borderColor: "#ffe69c" }}>
              <strong>RAG retrieval suggestions</strong>
              <div style={{ opacity: 0.7, fontSize: "0.85rem", marginBottom: 6 }}>
                These are NOT prompt fixes — they signal that the indexing pipeline needs work.
              </div>
              {analyzer.rag_suggestions.map((r, idx) => (
                <div key={idx} style={{ marginTop: 6 }}>
                  <strong>{r.type}</strong>: {r.description}
                  <span style={{ opacity: 0.6, marginLeft: 6 }}>({r.affected_ids.length} affected)</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const cardStyle: React.CSSProperties = {
  border: "1px solid rgba(0,0,0,0.12)",
  borderRadius: 8,
  padding: "14px 16px",
  background: "rgba(255,255,255,0.6)",
};

const btnStyle: React.CSSProperties = {
  padding: "6px 12px",
  borderRadius: 6,
  border: "1px solid rgba(0,0,0,0.2)",
  cursor: "pointer",
};
