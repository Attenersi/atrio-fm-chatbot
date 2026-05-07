"use client";

import { type CSSProperties, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  adminBulkTrainingExamplesReview,
  adminBuildTrainingV1Files,
  adminExportTrainingV1Jsonl,
  adminGetTrainingV1Manifest,
  adminListTrainingV1Exports,
  adminListTrainingExamples,
  adminUpdateTrainingExample,
  getSession,
  type TrainingV1ExportFile,
  type TrainingExample,
} from "../../../../lib/api";

function normalizeReviewStatus(value: string) {
  if (value === "corrected") return "edited";
  return value;
}

const STATUSES = ["pending", "approved", "edited", "rejected"] as const;
const CATEGORIES = ["General", "Safety", "Plumbing", "HVAC", "Electrical"] as const;
const PRIORITIES = ["LOW", "NORMAL", "HIGH", "URGENT"] as const;

function parseBulkIds(raw: string): number[] {
  const seen = new Set<number>();
  const out: number[] = [];
  for (const part of raw.split(/[\s,;]+/)) {
    const t = part.trim();
    if (!t) continue;
    const n = Number.parseInt(t, 10);
    if (!Number.isFinite(n) || n <= 0 || seen.has(n)) continue;
    seen.add(n);
    out.push(n);
  }
  return out;
}

export default function AdminTrainingReviewPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [rows, setRows] = useState<TrainingExample[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [idQuery, setIdQuery] = useState("");
  const [editMode, setEditMode] = useState(false);
  const [editedEntry, setEditedEntry] = useState<TrainingExample | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState("Loading training examples...");
  const [manifest, setManifest] = useState<Record<string, any> | null>(null);
  const [showStats, setShowStats] = useState(false);
  const [showExports, setShowExports] = useState(false);
  const [exportsList, setExportsList] = useState<TrainingV1ExportFile[]>([]);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkIdsRaw, setBulkIdsRaw] = useState("");
  const [bulkHumanNotes, setBulkHumanNotes] = useState("");
  const [bulkReasoning, setBulkReasoning] = useState("");
  const [bulkCorrectionType, setBulkCorrectionType] = useState<(typeof STATUSES)[number] | "">("");
  const [bulkBusy, setBulkBusy] = useState(false);

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") {
          router.replace("/chat");
          return;
        }
        setReady(true);
        void loadRows();
      })
      .catch(() => router.replace("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    const idTrimmed = idQuery.trim();
    const parsedId = Number.parseInt(idTrimmed, 10);
    const hasIdFilter = idTrimmed !== "" && Number.isInteger(parsedId);
    return rows.filter((r) => {
      if (statusFilter !== "all" && normalizeReviewStatus(r.correction_type) !== statusFilter) return false;
      if (hasIdFilter && r.id !== parsedId) return false;
      if (!q) return true;
      return (
        r.input_text.toLowerCase().includes(q) ||
        String(r.ideal_output?.category ?? "").toLowerCase().includes(q) ||
        String(r.ideal_output?.issue_summary ?? "").toLowerCase().includes(q)
      );
    });
  }, [rows, search, idQuery, statusFilter]);

  useEffect(() => {
    setCurrentIndex((i) => Math.min(i, Math.max(0, filtered.length - 1)));
  }, [filtered.length]);

  async function loadRows() {
    setLoading(true);
    setStatus("Loading training examples...");
    try {
      // Filtering by status happens locally via `filtered` so the user can
      // switch tabs without a network round trip; pull all rows once.
      const res = await adminListTrainingExamples({
        limit: 1000,
        offset: 0,
      });
      setRows(res.examples);
      try {
        const m = await adminGetTrainingV1Manifest();
        setManifest(m?.manifest ?? null);
      } catch {
        setManifest(null);
      }
      try {
        const ex = await adminListTrainingV1Exports(20);
        setExportsList(ex.exports ?? []);
      } catch {
        setExportsList([]);
      }
      setCurrentIndex(0);
      setStatus(`Loaded ${res.examples.length} examples.`);
    } catch (err) {
      setStatus(`Load failed: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  const currentEntry = filtered[currentIndex] ?? null;

  function syncRow(updated: TrainingExample) {
    setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  }

  async function submitReview(entry: TrainingExample, nextCorrectionType: "pending" | "approved" | "edited" | "rejected") {
    setSaving(true);
    setStatus(`Saving #${entry.id}...`);
    try {
      const res = await adminUpdateTrainingExample(entry.id, {
        correction_type: nextCorrectionType,
        ideal_output: entry.ideal_output ?? {},
        context_used: entry.context_used ?? [],
        human_notes: entry.human_notes ?? "",
        reasoning: entry.reasoning ?? "",
      });
      const updated = res.example;
      syncRow(updated);
      setStatus(`Saved #${updated.id} as ${normalizeReviewStatus(updated.correction_type)}.`);
    } catch (err) {
      setStatus(`Save failed: ${(err as Error).message}`);
    } finally {
      setSaving(false);
    }
  }

  function startEdit() {
    if (!currentEntry) return;
    setEditedEntry(JSON.parse(JSON.stringify(currentEntry)));
    setEditMode(true);
  }

  function cancelEdit() {
    setEditMode(false);
    setEditedEntry(null);
  }

  async function saveEdit() {
    if (!editedEntry) return;
    const editedPayload: TrainingExample = {
      ...editedEntry,
      correction_type: "edited",
    };
    await submitReview(editedPayload, "edited");
    setEditMode(false);
    setEditedEntry(null);
  }

  function buildBulkBody(): {
    ids: number[];
    human_notes?: string;
    reasoning?: string;
    correction_type?: (typeof STATUSES)[number];
  } | null {
    const ids = parseBulkIds(bulkIdsRaw);
    const hasNotes = bulkHumanNotes.trim() !== "";
    const hasReasoning = bulkReasoning.trim() !== "";
    const hasStatus = bulkCorrectionType !== "";
    if (!ids.length || (!hasNotes && !hasReasoning && !hasStatus)) return null;
    const body: {
      ids: number[];
      human_notes?: string;
      reasoning?: string;
      correction_type?: (typeof STATUSES)[number];
    } = { ids };
    if (hasNotes) body.human_notes = bulkHumanNotes;
    if (hasReasoning) body.reasoning = bulkReasoning;
    if (hasStatus) body.correction_type = bulkCorrectionType;
    return body;
  }

  async function runBulkPreview() {
    const body = buildBulkBody();
    if (!body) {
      setStatus("Bulk: paste at least one valid ID and set Status and/or Human notes and/or Reasoning.");
      return;
    }
    setBulkBusy(true);
    setStatus("Bulk preview…");
    try {
      const res = await adminBulkTrainingExamplesReview(body, { dryRun: true });
      const miss = res.missing_ids?.length
        ? ` Missing IDs: ${res.missing_ids.slice(0, 25).join(", ")}${res.missing_ids.length > 25 ? "…" : ""}.`
        : "";
      setStatus(`Preview: would update ${res.would_update ?? 0} of ${res.ids_requested} IDs.${miss}`);
    } catch (err) {
      setStatus(`Bulk preview failed: ${(err as Error).message}`);
    } finally {
      setBulkBusy(false);
    }
  }

  async function runBulkApply() {
    const body = buildBulkBody();
    if (!body) {
      setStatus("Bulk: paste at least one valid ID and set Status and/or Human notes and/or Reasoning.");
      return;
    }
    const statusHint =
      body.correction_type != null
        ? `Status → ${body.correction_type}.`
        : body.human_notes != null || body.reasoning != null
          ? "Notes/reasoning only → status becomes edited."
          : "";
    if (
      !window.confirm(
        `Apply bulk update to ${body.ids.length} example(s)? ${statusHint} Continue?`
      )
    ) {
      return;
    }
    setBulkBusy(true);
    setStatus("Bulk apply…");
    try {
      const res = await adminBulkTrainingExamplesReview(body, { confirm: true });
      const miss = res.missing_ids?.length
        ? ` Missing IDs: ${res.missing_ids.slice(0, 25).join(", ")}${res.missing_ids.length > 25 ? "…" : ""}.`
        : "";
      setStatus(`Bulk: updated ${res.updated} row(s).${miss}`);
      await loadRows();
    } catch (err) {
      setStatus(`Bulk apply failed: ${(err as Error).message}`);
    } finally {
      setBulkBusy(false);
    }
  }

  async function quickApprove() {
    if (!currentEntry) return;
    const updated: TrainingExample = {
      ...currentEntry,
      correction_type: "approved",
      human_notes:
        currentEntry.human_notes === "Auto-approved from passing test case." || !currentEntry.human_notes
          ? "Reviewed and approved - no changes needed."
          : currentEntry.human_notes,
    };
    await submitReview(updated, "approved");
    if (currentIndex < filtered.length - 1) setCurrentIndex(currentIndex + 1);
  }

  async function quickReject() {
    if (!currentEntry) return;
    const updated: TrainingExample = { ...currentEntry, correction_type: "rejected" };
    await submitReview(updated, "rejected");
    if (currentIndex < filtered.length - 1) setCurrentIndex(currentIndex + 1);
  }

  function downloadText(filename: string, content: string) {
    const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function exportV1Jsonl() {
    setStatus("Exporting v1 JSONL...");
    try {
      const content = await adminExportTrainingV1Jsonl();
      downloadText("fine_tuning_v1_train.jsonl", content);
      setStatus("Exported v1 JSONL.");
      await refreshExports();
    } catch (err) {
      setStatus(`Export failed: ${(err as Error).message}`);
    }
  }

  async function refreshExports() {
    try {
      const ex = await adminListTrainingV1Exports(20);
      setExportsList(ex.exports ?? []);
    } catch {
      setExportsList([]);
    }
  }

  async function saveFileSnapshot() {
    setStatus("Saving dataset file...");
    try {
      const res = await adminBuildTrainingV1Files();
      const manifest = res?.manifest ?? {};
      setStatus(
        `Saved. ${manifest.total_raw_rows ?? 0} total records, ${manifest.train_rows ?? 0} edited train records.`
      );
      try {
        const m = await adminGetTrainingV1Manifest();
        setManifest(m?.manifest ?? null);
      } catch {
        setManifest(null);
      }
      await refreshExports();
    } catch (err) {
      setStatus(`Build failed: ${(err as Error).message}`);
    }
  }

  const stats = useMemo(() => {
    const base = {
      total: rows.length,
      pending: 0,
      approved: 0,
      edited: 0,
      rejected: 0,
      kg: 0,
    };
    for (const row of rows) {
      const raw = String(row.correction_type || "");
      const s = normalizeReviewStatus(raw);
      if (s === "pending") base.pending += 1;
      else if (s === "approved") base.approved += 1;
      else if (s === "edited") base.edited += 1;
      else if (s === "rejected") base.rejected += 1;
      if (row.knowledge_gap_logged) base.kg += 1;
    }
    return base;
  }, [rows]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const tag = target?.tagName?.toLowerCase();
      const typing =
        !!target?.isContentEditable || tag === "input" || tag === "textarea" || tag === "select";
      if (typing) return;
      if (editMode) return;
      if (filtered.length === 0) return;
      const key = event.key.toLowerCase();
      if (key === "arrowleft" || key === "k") {
        event.preventDefault();
        setCurrentIndex((i) => Math.max(0, i - 1));
        return;
      }
      if (key === "arrowright" || key === "j") {
        event.preventDefault();
        setCurrentIndex((i) => Math.min(filtered.length - 1, i + 1));
        return;
      }
      if (key === "e") {
        event.preventDefault();
        startEdit();
        return;
      }
      if (!currentEntry || saving) return;
      if (key === "a") {
        event.preventDefault();
        void quickApprove();
      } else if (key === "r") {
        event.preventDefault();
        void quickReject();
      } else if (key === "p" || key === "n") {
        event.preventDefault();
        const updated: TrainingExample = { ...currentEntry, correction_type: "pending" };
        void submitReview(updated, "pending");
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filtered, saving, currentEntry, editMode, currentIndex]);

  if (!ready) {
    return (
      <section className="page-shell">
        <h1>Training Review</h1>
        <p className="text-muted">Checking admin session...</p>
      </section>
    );
  }

  if (loading) {
    return (
      <div style={s.container}>
        <div style={s.center}>
          <p style={{ color: "#94a3b8" }}>Loading data from server...</p>
        </div>
      </div>
    );
  }

  if (!rows.length) {
    return (
      <div style={s.container}>
        <div style={s.center}>
          <h1 style={s.logo}>FM Review Tool</h1>
          <p style={{ color: "#94a3b8", marginBottom: 16 }}>No entries found.</p>
        </div>
      </div>
    );
  }

  return (
    <div style={s.container}>
      <div style={s.header}>
        <div style={s.row}>
          <h1 style={s.logo}>FM Review Tool</h1>
          <span style={s.badgeWarn}>{stats.pending} pending</span>
          <span style={s.badgeOk}>{stats.approved + stats.edited} done</span>
          <span style={s.badgeInfo}>{stats.edited} edited</span>
          <span style={s.badgeDanger}>{stats.rejected} rejected</span>
        </div>
        <div style={s.row}>
          <span style={{ color: "#64748b", fontSize: 12 }}>{status}</span>
          <button onClick={() => setShowStats(!showStats)} style={showStats ? { ...s.btnGhost, ...s.btnGhostActive } : s.btnGhost}>
            Stats
          </button>
          <button onClick={() => { setShowExports((v) => !v); void refreshExports(); }} style={showExports ? { ...s.btnGhost, ...s.btnGhostActive } : s.btnGhost}>
            Saved exports
          </button>
          <button onClick={() => void saveFileSnapshot()} style={s.btnGhost}>Save file</button>
          <button onClick={() => void exportV1Jsonl()} style={s.btnGhost}>Export train (edited)</button>
        </div>
      </div>

      {showStats && (
        <div style={s.panel}>
          <div style={s.statsGrid}>
            {[
              ["Total", stats.total, "#f8fafc"],
              ["Pending", stats.pending, "#d97706"],
              ["Approved", stats.approved, "#16a34a"],
              ["Edited", stats.edited, "#7c3aed"],
              ["Rejected", stats.rejected, "#dc2626"],
            ].map(([label, val, color]) => (
              <div key={String(label)} style={s.statCard}>
                <div style={{ fontSize: 28, fontWeight: 700, color: String(color) }}>{String(val)}</div>
                <div style={s.statLabel}>{String(label)}</div>
              </div>
            ))}
          </div>
          <div style={{ color: "#94a3b8", fontSize: 12, marginTop: 6 }}>
            Version: {String(manifest?.version ?? "n/a")} · Updated: {String(manifest?.updated_at ?? "n/a")}
          </div>
        </div>
      )}

      {showExports && (
        <div style={s.panel}>
          <div style={{ color: "#94a3b8", fontSize: 12, marginBottom: 8 }}>Latest exports (backend/data)</div>
          {exportsList.length === 0 ? (
            <div style={{ color: "#64748b", fontSize: 13 }}>No export files found.</div>
          ) : (
            <div style={{ display: "grid", gap: 6 }}>
              {exportsList.map((it) => (
                <div key={`${it.name}-${it.updated_at}`} style={{ ...s.fieldBox, fontSize: 12 }}>
                  {it.name} · {Math.round((it.size_bytes || 0) / 1024)} KB · {it.updated_at}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ marginBottom: 10 }}>
        <div style={s.filterBar}>
          <div style={s.row}>
            {[...STATUSES, "all"].map((key) => (
              <button
                key={key}
                onClick={() => {
                  setStatusFilter(key);
                  setCurrentIndex(0);
                }}
                style={statusFilter === key ? { ...s.tab, ...s.tabActive } : s.tab}
              >
                {key}
              </button>
            ))}
          </div>
          <div style={s.searchGroup}>
            <input type="text" inputMode="numeric" value={idQuery} onChange={(e) => { setIdQuery(e.target.value); setCurrentIndex(0); }} placeholder="Search ID..." style={s.searchInputSmall} />
            <input type="text" value={search} onChange={(e) => { setSearch(e.target.value); setCurrentIndex(0); }} placeholder="Search text..." style={s.searchInput} />
          </div>
        </div>
        <div style={{ marginTop: 8 }}>
          <button
            type="button"
            onClick={() => setBulkOpen((v) => !v)}
            style={bulkOpen ? { ...s.btnGhost, ...s.btnGhostActive } : s.btnGhost}
          >
            {bulkOpen ? "Hide bulk by ID" : "Bulk by ID"}
          </button>
        </div>
        {bulkOpen && (
          <div style={{ ...s.panel, marginTop: 10 }}>
            <div style={s.sectionLabel}>Bulk update by ID (status, notes, reasoning)</div>
            <p style={{ color: "#64748b", fontSize: 12, margin: "0 0 12px" }}>
              Paste IDs (comma, space, or newline). Choose at least one of: <strong style={{ color: "#94a3b8" }}>Status</strong>, Human
              notes, or Reasoning. If you change only notes/reasoning, status becomes <strong style={{ color: "#94a3b8" }}>edited</strong>.
              Max 500 IDs per request.
            </p>
            <label style={s.editLabel}>IDs</label>
            <textarea
              value={bulkIdsRaw}
              onChange={(e) => setBulkIdsRaw(e.target.value)}
              rows={4}
              style={s.textarea}
              placeholder="e.g. 430, 418, 405"
              disabled={bulkBusy}
            />
            <div style={{ marginTop: 12 }}>
              <label style={s.editLabel}>Status (optional)</label>
              <select
                value={bulkCorrectionType}
                onChange={(e) => setBulkCorrectionType((e.target.value || "") as (typeof STATUSES)[number] | "")}
                style={s.select}
                disabled={bulkBusy}
              >
                <option value="">No change (notes/reasoning only still force edited)</option>
                {STATUSES.map((st) => (
                  <option key={st} value={st}>
                    {st}
                  </option>
                ))}
              </select>
            </div>
            <div style={{ marginTop: 12 }}>
              <label style={s.editLabel}>Human notes (optional if Reasoning set)</label>
              <textarea
                value={bulkHumanNotes}
                onChange={(e) => setBulkHumanNotes(e.target.value)}
                rows={3}
                style={s.textarea}
                disabled={bulkBusy}
              />
            </div>
            <div style={{ marginTop: 12 }}>
              <label style={s.editLabel}>Reasoning (optional if Human notes set)</label>
              <textarea
                value={bulkReasoning}
                onChange={(e) => setBulkReasoning(e.target.value)}
                rows={3}
                style={s.textarea}
                disabled={bulkBusy}
              />
            </div>
            <div style={{ ...s.actions, padding: "12px 0 0", marginTop: 8 }}>
              <button type="button" onClick={() => void runBulkPreview()} disabled={bulkBusy} style={s.btnGhost}>
                Preview
              </button>
              <button type="button" onClick={() => void runBulkApply()} disabled={bulkBusy} style={s.btnPrimary}>
                Apply
              </button>
            </div>
          </div>
        )}
      </div>

      <div style={s.navBar}>
        <button onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))} disabled={currentIndex === 0} style={{ ...s.btnNav, opacity: currentIndex === 0 ? 0.3 : 1 }}>
          ← Previous
        </button>
        <span style={{ color: "#94a3b8", fontSize: 13 }}>
          {filtered.length > 0 ? `${currentIndex + 1} / ${filtered.length}` : "No results"}
          {currentEntry && ` · ID ${currentEntry.id}`}
        </span>
        <button onClick={() => setCurrentIndex(Math.min(filtered.length - 1, currentIndex + 1))} disabled={currentIndex >= filtered.length - 1} style={{ ...s.btnNav, opacity: currentIndex >= filtered.length - 1 ? 0.3 : 1 }}>
          Next →
        </button>
      </div>

      {currentEntry && !editMode && (
        <div style={s.card}>
          <div style={{ ...s.actions, marginBottom: 4, justifyContent: "flex-end", paddingTop: 0 }}>
            <button onClick={startEdit} style={s.btnEdit}>
              Edit (E)
            </button>
          </div>
          <Section label="Tenant message">
            <div style={s.tenantMsg}>{currentEntry.input_text}</div>
          </Section>

          <Section label="Model response">
            <div style={s.tagGrid}>
              <Tag label="Category" value={String(currentEntry.ideal_output?.category ?? currentEntry.actual_output?.category ?? "General")} />
              <Tag label="Priority" value={String(currentEntry.ideal_output?.priority ?? currentEntry.actual_output?.priority ?? "NORMAL")} />
              <Tag label="Ticket" value={(currentEntry.ideal_output?.create_ticket ?? currentEntry.actual_output?.create_ticket) ? "YES" : "NO"} />
              <Tag label="Status" value={normalizeReviewStatus(currentEntry.correction_type)} />
            </div>
            <Field label="Response" value={String(currentEntry.ideal_output?.response ?? currentEntry.actual_output?.response ?? "")} />
            <Field label="Issue summary" value={String(currentEntry.ideal_output?.issue_summary ?? currentEntry.actual_output?.issue_summary ?? "")} />
          </Section>

          <Section label="Review">
            <Field label="Human notes" value={currentEntry.human_notes || "-"} italic />
            <Field label="Reasoning" value={currentEntry.reasoning || "-"} italic />
          </Section>
        </div>
      )}

      {editMode && editedEntry && (
        <div style={s.card}>
          <div style={{ ...s.actions, marginBottom: 4, justifyContent: "flex-end", paddingTop: 0 }}>
            <button onClick={() => void saveEdit()} disabled={saving} style={s.btnPrimary}>
              Save changes
            </button>
          </div>
          <Section label="Tenant message">
            <div style={s.tenantMsg}>{editedEntry.input_text}</div>
          </Section>

          <Section label="Edit response">
            <div style={s.editGrid}>
              <EditSelect
                label="Category"
                value={String(editedEntry.ideal_output?.category ?? "")}
                options={CATEGORIES}
                onChange={(v) => setEditedEntry({ ...editedEntry, ideal_output: { ...editedEntry.ideal_output, category: v } })}
              />
              <EditSelect
                label="Priority"
                value={String(editedEntry.ideal_output?.priority ?? "")}
                options={PRIORITIES}
                onChange={(v) => setEditedEntry({ ...editedEntry, ideal_output: { ...editedEntry.ideal_output, priority: v } })}
              />
              <EditSelect
                label="Ticket"
                value={String(Boolean(editedEntry.ideal_output?.create_ticket))}
                options={["true", "false"]}
                onChange={(v) => setEditedEntry({ ...editedEntry, ideal_output: { ...editedEntry.ideal_output, create_ticket: v === "true" } })}
              />
              <EditSelect
                label="Status"
                value={normalizeReviewStatus(editedEntry.correction_type)}
                options={STATUSES}
                onChange={(v) => setEditedEntry({ ...editedEntry, correction_type: v as any })}
              />
            </div>
            <div style={{ marginTop: 16 }}>
              <label style={s.editLabel}>Response</label>
              <textarea value={String(editedEntry.ideal_output?.response ?? "")} rows={4} style={s.textarea} onChange={(e) => setEditedEntry({ ...editedEntry, ideal_output: { ...editedEntry.ideal_output, response: e.target.value } })} />
            </div>
            <div style={{ marginTop: 12 }}>
              <label style={s.editLabel}>Issue summary</label>
              <input type="text" value={String(editedEntry.ideal_output?.issue_summary ?? "")} style={s.input} onChange={(e) => setEditedEntry({ ...editedEntry, ideal_output: { ...editedEntry.ideal_output, issue_summary: e.target.value } })} />
            </div>
          </Section>

          <Section label="Review notes">
            <div style={{ marginBottom: 12 }}>
              <label style={s.editLabel}>Human Notes</label>
              <textarea value={editedEntry.human_notes || ""} rows={3} style={s.textarea} onChange={(e) => setEditedEntry({ ...editedEntry, human_notes: e.target.value })} />
            </div>
            <div>
              <label style={s.editLabel}>Reasoning</label>
              <textarea value={editedEntry.reasoning || ""} rows={3} style={s.textarea} onChange={(e) => setEditedEntry({ ...editedEntry, reasoning: e.target.value })} />
            </div>
          </Section>

          <div style={s.actions}>
            <button onClick={() => void saveEdit()} disabled={saving} style={s.btnPrimary}>
              Save changes
            </button>
            <button onClick={cancelEdit} disabled={saving} style={s.btnGhost}>
              Cancel
            </button>
          </div>
        </div>
      )}

      <div style={s.shortcuts}>Left/Right or J/K navigate · E edit · A approve · R reject</div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={s.section}>
      <div style={s.sectionLabel}>{label}</div>
      {children}
    </div>
  );
}

function Tag({ label, value }: { label: string; value: string }) {
  return (
    <div style={s.tagBox}>
      <div style={s.tagLabel}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "#f8fafc" }}>{value}</div>
    </div>
  );
}

function Field({ label, value, italic }: { label: string; value: string; italic?: boolean }) {
  return (
    <div style={{ marginTop: 10 }}>
      <div style={s.miniLabel}>{label}</div>
      <div style={{ ...s.fieldBox, fontStyle: italic ? "italic" : "normal" }}>{value}</div>
    </div>
  );
}

function EditSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: readonly string[] | string[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label style={s.editLabel}>{label}</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} style={s.select}>
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}

const s: Record<string, CSSProperties> = {
  container: { fontFamily: "'JetBrains Mono', 'SF Mono', monospace", maxWidth: 920, margin: "0 auto", padding: 20, color: "#e2e8f0", background: "#0a0f1a", minHeight: "100vh" },
  center: { display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "60vh" },
  logo: { fontSize: 20, fontWeight: 700, color: "#f8fafc", margin: 0, letterSpacing: -0.5 },
  header: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8 },
  row: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  badgeWarn: { background: "#92400e", color: "#fbbf24", fontSize: 11, fontWeight: 600, padding: "2px 10px", borderRadius: 10 },
  badgeOk: { background: "#14532d", color: "#4ade80", fontSize: 11, fontWeight: 600, padding: "2px 10px", borderRadius: 10 },
  badgeInfo: { background: "#1e3a8a", color: "#93c5fd", fontSize: 11, fontWeight: 600, padding: "2px 10px", borderRadius: 10 },
  badgeDanger: { background: "#450a0a", color: "#fca5a5", fontSize: 11, fontWeight: 600, padding: "2px 10px", borderRadius: 10 },
  panel: { background: "#111827", border: "1px solid #1f2937", borderRadius: 10, padding: 20, marginBottom: 14 },
  statsGrid: { display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 },
  statCard: { background: "#1e293b", padding: 14, borderRadius: 8, textAlign: "center" },
  statLabel: { fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 1, marginTop: 4 },
  filterBar: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, gap: 10, flexWrap: "wrap" },
  tab: { background: "transparent", border: "1px solid #1f2937", color: "#94a3b8", fontSize: 12, padding: "5px 12px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit" },
  tabActive: { background: "#1e293b", color: "#f8fafc", borderColor: "#475569" },
  searchGroup: { display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" },
  searchInputSmall: { background: "#111827", border: "1px solid #1f2937", color: "#e2e8f0", fontSize: 13, padding: "6px 12px", borderRadius: 6, width: 120, outline: "none", fontFamily: "inherit" },
  searchInput: { background: "#111827", border: "1px solid #1f2937", color: "#e2e8f0", fontSize: 13, padding: "6px 12px", borderRadius: 6, width: 180, outline: "none", fontFamily: "inherit" },
  navBar: { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10, padding: "6px 0" },
  btnNav: { background: "transparent", border: "1px solid #1f2937", color: "#94a3b8", fontSize: 12, padding: "5px 14px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit" },
  card: { background: "#111827", border: "1px solid #1f2937", borderRadius: 10, overflow: "hidden" },
  section: { padding: "16px 20px", borderBottom: "1px solid #1f2937" },
  sectionLabel: { fontSize: 10, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: 1.5, marginBottom: 10 },
  tenantMsg: { fontSize: 14, lineHeight: 1.65, color: "#f1f5f9", background: "#1e293b", padding: "12px 16px", borderRadius: 8, borderLeft: "3px solid #3b82f6" },
  tagGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 },
  tagBox: { background: "#1e293b", padding: "8px 12px", borderRadius: 6, textAlign: "center" },
  tagLabel: { fontSize: 9, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 3 },
  miniLabel: { fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 },
  fieldBox: { fontSize: 13, lineHeight: 1.5, color: "#cbd5e1", background: "#1e293b", padding: "10px 14px", borderRadius: 6 },
  editGrid: { display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 },
  editLabel: { display: "block", fontSize: 10, color: "#64748b", textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 },
  input: { width: "100%", background: "#1e293b", border: "1px solid #334155", color: "#e2e8f0", fontSize: 13, padding: "8px 12px", borderRadius: 6, outline: "none", fontFamily: "inherit", boxSizing: "border-box" },
  select: { width: "100%", background: "#1e293b", border: "1px solid #334155", color: "#e2e8f0", fontSize: 13, padding: "8px 12px", borderRadius: 6, outline: "none", fontFamily: "inherit", boxSizing: "border-box" },
  textarea: { width: "100%", background: "#1e293b", border: "1px solid #334155", color: "#e2e8f0", fontSize: 13, padding: "10px 12px", borderRadius: 6, outline: "none", fontFamily: "inherit", resize: "vertical", lineHeight: 1.5, boxSizing: "border-box" },
  actions: { padding: "14px 20px", display: "flex", gap: 8, flexWrap: "wrap" },
  btnPrimary: { background: "#2563eb", color: "#fff", border: "none", fontSize: 13, fontWeight: 600, padding: "8px 20px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit" },
  btnGhost: { background: "transparent", border: "1px solid #1f2937", color: "#94a3b8", fontSize: 12, padding: "6px 14px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit" },
  btnGhostActive: { background: "#1e293b", color: "#f8fafc", borderColor: "#475569" },
  btnEdit: { background: "#1e293b", border: "1px solid #475569", color: "#e2e8f0", fontSize: 13, fontWeight: 600, padding: "8px 20px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit" },
  btnApprove: { background: "#14532d", border: "1px solid #16a34a", color: "#4ade80", fontSize: 13, fontWeight: 600, padding: "8px 20px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit" },
  btnReject: { background: "#450a0a", border: "1px solid #dc2626", color: "#f87171", fontSize: 13, fontWeight: 600, padding: "8px 20px", borderRadius: 6, cursor: "pointer", fontFamily: "inherit" },
  shortcuts: { textAlign: "center", color: "#334155", fontSize: 11, marginTop: 16, padding: 8 },
};

