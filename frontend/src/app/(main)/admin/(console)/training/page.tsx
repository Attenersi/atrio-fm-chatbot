"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useI18n } from "../../../../../i18n/I18nProvider";
import {
  adminBulkTrainingExamplesReview,
  adminBuildTrainingV1Files,
  adminExportTrainingExamplesFiltered,
  adminExportTrainingV1Jsonl,
  adminGetTrainingV1Manifest,
  adminListTrainingV1Exports,
  adminListTrainingExamples,
  adminUpdateTrainingExample,
  getSession,
  type TrainingV1ExportFile,
  type TrainingExample,
} from "../../../../../lib/api";

function normalizeReviewStatus(value: string) {
  if (value === "corrected") return "edited";
  return value;
}

const STATUSES = ["pending", "approved", "edited", "rejected"] as const;
const CATEGORIES = [
  "General",
  "Safety",
  "Plumbing",
  "HVAC",
  "Electrical",
] as const;
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

/** Convert `<input type="datetime-local">` value to UTC ISO for `created_at` string compare on the server. */
function datetimeLocalToIsoUtc(value: string): string | null {
  const v = value.trim();
  if (!v) return null;
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

export default function AdminTrainingReviewPage() {
  const { t } = useI18n();
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
  const [showExportPanel, setShowExportPanel] = useState(false);
  const [exportKind, setExportKind] = useState<"filtered" | "v1_train">(
    "filtered"
  );
  const [exportCorr, setExportCorr] = useState<Record<string, boolean>>({
    pending: true,
    approved: true,
    edited: true,
    rejected: true,
  });
  const [exportIdsRaw, setExportIdsRaw] = useState("");
  const [exportIdMin, setExportIdMin] = useState("");
  const [exportIdMax, setExportIdMax] = useState("");
  const [exportCreatedAfter, setExportCreatedAfter] = useState("");
  const [exportCreatedBefore, setExportCreatedBefore] = useState("");
  const [exportIncludeActual, setExportIncludeActual] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [exportsList, setExportsList] = useState<TrainingV1ExportFile[]>([]);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [bulkIdsRaw, setBulkIdsRaw] = useState("");
  const [bulkHumanNotes, setBulkHumanNotes] = useState("");
  const [bulkReasoning, setBulkReasoning] = useState("");
  const [bulkCorrectionType, setBulkCorrectionType] = useState<
    (typeof STATUSES)[number] | ""
  >("");
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
      if (
        statusFilter !== "all" &&
        normalizeReviewStatus(r.correction_type) !== statusFilter
      )
        return false;
      if (hasIdFilter && r.id !== parsedId) return false;
      if (!q) return true;
      return (
        r.input_text.toLowerCase().includes(q) ||
        String(r.ideal_output?.category ?? "")
          .toLowerCase()
          .includes(q) ||
        String(r.ideal_output?.issue_summary ?? "")
          .toLowerCase()
          .includes(q)
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

  async function submitReview(
    entry: TrainingExample,
    nextCorrectionType: "pending" | "approved" | "edited" | "rejected"
  ) {
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
      setStatus(
        `Saved #${updated.id} as ${normalizeReviewStatus(updated.correction_type)}.`
      );
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
      setStatus(
        "Bulk: paste at least one valid ID and set Status and/or Human notes and/or Reasoning."
      );
      return;
    }
    setBulkBusy(true);
    setStatus("Bulk preview…");
    try {
      const res = await adminBulkTrainingExamplesReview(body, { dryRun: true });
      const miss = res.missing_ids?.length
        ? ` Missing IDs: ${res.missing_ids.slice(0, 25).join(", ")}${res.missing_ids.length > 25 ? "…" : ""}.`
        : "";
      setStatus(
        `Preview: would update ${res.would_update ?? 0} of ${res.ids_requested} IDs.${miss}`
      );
    } catch (err) {
      setStatus(`Bulk preview failed: ${(err as Error).message}`);
    } finally {
      setBulkBusy(false);
    }
  }

  async function runBulkApply() {
    const body = buildBulkBody();
    if (!body) {
      setStatus(
        "Bulk: paste at least one valid ID and set Status and/or Human notes and/or Reasoning."
      );
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
      const res = await adminBulkTrainingExamplesReview(body, {
        confirm: true,
      });
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
        currentEntry.human_notes === "Auto-approved from passing test case." ||
        !currentEntry.human_notes
          ? "Reviewed and approved - no changes needed."
          : currentEntry.human_notes,
    };
    await submitReview(updated, "approved");
    if (currentIndex < filtered.length - 1) setCurrentIndex(currentIndex + 1);
  }

  async function quickReject() {
    if (!currentEntry) return;
    const updated: TrainingExample = {
      ...currentEntry,
      correction_type: "rejected",
    };
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

  async function runExportFromPanel() {
    if (exportKind === "v1_train") {
      setExportBusy(true);
      setStatus("Exporting v1 train JSONL...");
      try {
        const content = await adminExportTrainingV1Jsonl();
        downloadText("fine_tuning_v1_train.jsonl", content);
        setStatus("Exported v1 train JSONL.");
        await refreshExports();
      } catch (err) {
        setStatus(`Export failed: ${(err as Error).message}`);
      } finally {
        setExportBusy(false);
      }
      return;
    }

    const correction_types = STATUSES.filter((s) => exportCorr[s]);
    if (correction_types.length === 0) {
      setStatus("Select at least one correction type for export.");
      return;
    }

    const parsedIds = parseBulkIds(exportIdsRaw);
    const idMinTrim = exportIdMin.trim();
    const idMaxTrim = exportIdMax.trim();
    const id_min =
      idMinTrim === ""
        ? null
        : Number.isFinite(Number.parseInt(idMinTrim, 10))
          ? Number.parseInt(idMinTrim, 10)
          : null;
    const id_max =
      idMaxTrim === ""
        ? null
        : Number.isFinite(Number.parseInt(idMaxTrim, 10))
          ? Number.parseInt(idMaxTrim, 10)
          : null;
    if (
      (idMinTrim !== "" && id_min === null) ||
      (idMaxTrim !== "" && id_max === null)
    ) {
      setStatus("ID min/max must be valid integers when set.");
      return;
    }
    if (id_min !== null && id_max !== null && id_min > id_max) {
      setStatus("ID min must be less than or equal to ID max.");
      return;
    }

    const created_after = datetimeLocalToIsoUtc(exportCreatedAfter);
    const created_before = datetimeLocalToIsoUtc(exportCreatedBefore);

    setExportBusy(true);
    setStatus("Exporting filtered examples...");
    try {
      const content = await adminExportTrainingExamplesFiltered({
        correction_types,
        ids: parsedIds.length ? parsedIds : undefined,
        id_min: id_min ?? undefined,
        id_max: id_max ?? undefined,
        created_after: created_after ?? undefined,
        created_before: created_before ?? undefined,
        include_actual_output: exportIncludeActual,
      });
      const ts = new Date().toISOString().replace(/[:.]/g, "-");
      downloadText(`training_examples_export_${ts}.jsonl`, content);
      setStatus("Exported filtered training examples.");
      await refreshExports();
    } catch (err) {
      setStatus(`Export failed: ${(err as Error).message}`);
    } finally {
      setExportBusy(false);
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
        !!target?.isContentEditable ||
        tag === "input" ||
        tag === "textarea" ||
        tag === "select";
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
        const updated: TrainingExample = {
          ...currentEntry,
          correction_type: "pending",
        };
        void submitReview(updated, "pending");
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [filtered, saving, currentEntry, editMode, currentIndex]);

  if (!ready) {
    return (
      <section className="page-shell">
        <h1>{t("nav.trainingReview")}</h1>
        <p className="text-muted">Checking admin session...</p>
      </section>
    );
  }

  if (loading) {
    return (
      <section className="page-shell training-page-wrap">
        <div className="training-center-state">
          <p className="text-muted">Loading data from server...</p>
        </div>
      </section>
    );
  }

  if (!rows.length) {
    return (
      <section className="page-shell training-page-wrap">
        <div className="training-center-state">
          <h1 className="page-title-md">FM Review Tool</h1>
          <p className="text-muted u-mb-16">No entries found.</p>
        </div>
      </section>
    );
  }

  return (
    <section className="page-shell training-page-wrap">
      <div className="page-header-block">
        <div className="toolbar-spread-wrap">
          <div className="flex-wrap-gap-sm">
            <h1 className="page-title-md m-0">FM Review Tool</h1>
            <span className="training-badge training-badge--pending">
              {stats.pending} pending
            </span>
            <span className="training-badge training-badge--ok">
              {stats.approved + stats.edited} done
            </span>
            <span className="training-badge training-badge--info">
              {stats.edited} edited
            </span>
            <span className="training-badge training-badge--danger">
              {stats.rejected} rejected
            </span>
          </div>
          <div className="flex-wrap-gap-sm">
            <span className="text-muted training-review-fs12">{status}</span>
            <button
              type="button"
              className={`btn btn-ghost btn-sm${showStats ? " is-active" : ""}`}
              onClick={() => setShowStats(!showStats)}
            >
              Stats
            </button>
            <button
              type="button"
              className={`btn btn-ghost btn-sm${showExports ? " is-active" : ""}`}
              onClick={() => {
                setShowExports((v) => !v);
                void refreshExports();
              }}
            >
              Saved exports
            </button>
            <button
              type="button"
              className={`btn btn-ghost btn-sm${showExportPanel ? " is-active" : ""}`}
              onClick={() => setShowExportPanel((v) => !v)}
            >
              Export
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => void saveFileSnapshot()}
            >
              Save file
            </button>
          </div>
        </div>
      </div>

      {showExportPanel && (
        <div className="card u-mb-16">
          <div className="training-section-label u-mb-8">Export</div>
          <div className="stack-gap-8-mt">
            <div className="flex-wrap-gap-sm">
              <label className="training-review-fs12 flex items-center gap-6">
                <input
                  type="radio"
                  name="exportKind"
                  checked={exportKind === "filtered"}
                  onChange={() => setExportKind("filtered")}
                  disabled={exportBusy}
                />
                Filtered (database)
              </label>
              <label className="training-review-fs12 flex items-center gap-6">
                <input
                  type="radio"
                  name="exportKind"
                  checked={exportKind === "v1_train"}
                  onChange={() => setExportKind("v1_train")}
                  disabled={exportBusy}
                />
                V1 train (edited only)
              </label>
            </div>

            {exportKind === "filtered" && (
              <>
                <div>
                  <div className="training-edit-label u-mb-4">
                    Correction types
                  </div>
                  <div className="flex-wrap-gap-sm">
                    {STATUSES.map((st) => (
                      <label
                        key={st}
                        className="training-review-fs12 flex items-center gap-6"
                      >
                        <input
                          type="checkbox"
                          checked={exportCorr[st]}
                          onChange={(e) =>
                            setExportCorr((prev) => ({
                              ...prev,
                              [st]: e.target.checked,
                            }))
                          }
                          disabled={exportBusy}
                        />
                        {st}
                      </label>
                    ))}
                  </div>
                </div>
                <div className="training-edit-grid">
                  <div>
                    <label className="training-edit-label">ID min</label>
                    <input
                      type="text"
                      inputMode="numeric"
                      className="field w-full"
                      value={exportIdMin}
                      onChange={(e) => setExportIdMin(e.target.value)}
                      placeholder="optional"
                      disabled={exportBusy}
                    />
                  </div>
                  <div>
                    <label className="training-edit-label">ID max</label>
                    <input
                      type="text"
                      inputMode="numeric"
                      className="field w-full"
                      value={exportIdMax}
                      onChange={(e) => setExportIdMax(e.target.value)}
                      placeholder="optional"
                      disabled={exportBusy}
                    />
                  </div>
                </div>
                <div>
                  <label className="training-edit-label">Specific IDs</label>
                  <textarea
                    className="field w-full"
                    rows={3}
                    value={exportIdsRaw}
                    onChange={(e) => setExportIdsRaw(e.target.value)}
                    placeholder="Comma, space, or newline (optional)"
                    disabled={exportBusy}
                  />
                </div>
                <div className="training-edit-grid">
                  <div>
                    <label className="training-edit-label">
                      Created after (local)
                    </label>
                    <input
                      type="datetime-local"
                      className="field w-full"
                      value={exportCreatedAfter}
                      onChange={(e) => setExportCreatedAfter(e.target.value)}
                      disabled={exportBusy}
                    />
                  </div>
                  <div>
                    <label className="training-edit-label">
                      Created before (local)
                    </label>
                    <input
                      type="datetime-local"
                      className="field w-full"
                      value={exportCreatedBefore}
                      onChange={(e) => setExportCreatedBefore(e.target.value)}
                      disabled={exportBusy}
                    />
                  </div>
                </div>
                <label className="training-review-fs12 flex items-center gap-6">
                  <input
                    type="checkbox"
                    checked={exportIncludeActual}
                    onChange={(e) => setExportIncludeActual(e.target.checked)}
                    disabled={exportBusy}
                  />
                  Include raw <code className="text-primary">actual_output</code>
                </label>
                <p className="text-muted training-review-fs12 m-0">
                  Date filters are converted from your local time to UTC ISO for
                  comparison with stored <code>created_at</code> values.
                </p>
              </>
            )}

            {exportKind === "v1_train" && (
              <p className="text-muted training-review-fs12 m-0">
                Downloads the v1 edited-only train set (same as before). Does
                not use the filters above.
              </p>
            )}

            <div>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={exportBusy}
                onClick={() => void runExportFromPanel()}
              >
                {exportBusy ? "Exporting…" : "Download"}
              </button>
            </div>
          </div>
        </div>
      )}

      {showStats && (
        <div className="card u-mb-16">
          <div className="training-stats-grid">
            {(
              [
                ["Total", stats.total, "training-stat-value--total"],
                ["Pending", stats.pending, "training-stat-value--pending"],
                ["Approved", stats.approved, "training-stat-value--approved"],
                ["Edited", stats.edited, "training-stat-value--edited"],
                ["Rejected", stats.rejected, "training-stat-value--rejected"],
              ] as const
            ).map(([label, val, mod]) => (
              <div key={String(label)} className="training-stat-card">
                <div className={`training-stat-value ${mod}`}>
                  {String(val)}
                </div>
                <div className="training-stat-label">{String(label)}</div>
              </div>
            ))}
          </div>
          <div className="text-muted training-review-fs12 u-mt-6">
            Version: {String(manifest?.version ?? "n/a")} · Updated:{" "}
            {String(manifest?.updated_at ?? "n/a")}
          </div>
        </div>
      )}

      {showExports && (
        <div className="card u-mb-16">
          <div className="text-muted training-review-fs12 u-mb-8">
            Latest exports (backend/data)
          </div>
          {exportsList.length === 0 ? (
            <div className="text-muted training-review-fs13">
              No export files found.
            </div>
          ) : (
            <div className="stack-gap-8-mt">
              {exportsList.map((it) => (
                <div
                  key={`${it.name}-${it.updated_at}`}
                  className="training-field-box training-export-row"
                >
                  {it.name} · {Math.round((it.size_bytes || 0) / 1024)} KB ·{" "}
                  {it.updated_at}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="u-mb-10">
        <div className="training-filter-bar">
          <div className="flex-wrap-gap-sm">
            {[...STATUSES, "all"].map((key) => (
              <button
                type="button"
                key={key}
                className={`btn btn-ghost btn-sm${statusFilter === key ? " is-active" : ""}`}
                onClick={() => {
                  setStatusFilter(key);
                  setCurrentIndex(0);
                }}
              >
                {key}
              </button>
            ))}
          </div>
          <div className="flex-wrap-gap-sm">
            <input
              type="text"
              inputMode="numeric"
              className="field field-w-120"
              value={idQuery}
              onChange={(e) => {
                setIdQuery(e.target.value);
                setCurrentIndex(0);
              }}
              placeholder="Search ID..."
            />
            <input
              type="text"
              className="field field-w-180"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setCurrentIndex(0);
              }}
              placeholder="Search text..."
            />
          </div>
        </div>
        <div className="u-mt-8">
          <button
            type="button"
            className={`btn btn-ghost btn-sm${bulkOpen ? " is-active" : ""}`}
            onClick={() => setBulkOpen((v) => !v)}
          >
            {bulkOpen ? "Hide bulk by ID" : "Bulk by ID"}
          </button>
        </div>
        {bulkOpen && (
          <div className="card u-mt-10">
            <div className="training-section-label">
              Bulk update by ID (status, notes, reasoning)
            </div>
            <p className="text-muted training-review-fs12 m-0 u-mb-12">
              Paste IDs (comma, space, or newline). Choose at least one of:{" "}
              <strong className="text-primary">Status</strong>, Human notes, or
              Reasoning. If you change only notes/reasoning, status becomes{" "}
              <strong className="text-primary">edited</strong>. Max 500 IDs per
              request.
            </p>
            <label className="training-edit-label">IDs</label>
            <textarea
              className="field w-full"
              value={bulkIdsRaw}
              onChange={(e) => setBulkIdsRaw(e.target.value)}
              rows={4}
              placeholder="e.g. 430, 418, 405"
              disabled={bulkBusy}
            />
            <div className="u-mt-12">
              <label className="training-edit-label">Status (optional)</label>
              <select
                className="field"
                value={bulkCorrectionType}
                onChange={(e) =>
                  setBulkCorrectionType(
                    (e.target.value || "") as (typeof STATUSES)[number] | ""
                  )
                }
                disabled={bulkBusy}
              >
                <option value="">
                  No change (notes/reasoning only still force edited)
                </option>
                {STATUSES.map((st) => (
                  <option key={st} value={st}>
                    {st}
                  </option>
                ))}
              </select>
            </div>
            <div className="u-mt-12">
              <label className="training-edit-label">
                Human notes (optional if Reasoning set)
              </label>
              <textarea
                className="field w-full"
                value={bulkHumanNotes}
                onChange={(e) => setBulkHumanNotes(e.target.value)}
                rows={3}
                disabled={bulkBusy}
              />
            </div>
            <div className="u-mt-12">
              <label className="training-edit-label">
                Reasoning (optional if Human notes set)
              </label>
              <textarea
                className="field w-full"
                value={bulkReasoning}
                onChange={(e) => setBulkReasoning(e.target.value)}
                rows={3}
                disabled={bulkBusy}
              />
            </div>
            <div className="training-actions u-mt-8" style={{ paddingTop: 12 }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => void runBulkPreview()}
                disabled={bulkBusy}
              >
                Preview
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => void runBulkApply()}
                disabled={bulkBusy}
              >
                Apply
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="training-nav-bar">
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => setCurrentIndex(Math.max(0, currentIndex - 1))}
          disabled={currentIndex === 0}
        >
          ← Previous
        </button>
        <span className="training-nav-meta">
          {filtered.length > 0
            ? `${currentIndex + 1} / ${filtered.length}`
            : "No results"}
          {currentEntry && ` · ID ${currentEntry.id}`}
        </span>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() =>
            setCurrentIndex(Math.min(filtered.length - 1, currentIndex + 1))
          }
          disabled={currentIndex >= filtered.length - 1}
        >
          Next →
        </button>
      </div>

      {currentEntry && !editMode && (
        <div className="card overflow-hidden">
          <div className="training-actions training-actions--toolbar">
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={startEdit}
            >
              Edit (E)
            </button>
          </div>
          <Section label="Tenant message">
            <div className="training-tenant-msg">{currentEntry.input_text}</div>
          </Section>

          <Section label="Model response">
            <div className="training-tag-grid">
              <Tag
                label="Category"
                value={String(
                  currentEntry.ideal_output?.category ??
                    currentEntry.actual_output?.category ??
                    "General"
                )}
              />
              <Tag
                label="Priority"
                value={String(
                  currentEntry.ideal_output?.priority ??
                    currentEntry.actual_output?.priority ??
                    "NORMAL"
                )}
              />
              <Tag
                label="Ticket"
                value={
                  (currentEntry.ideal_output?.create_ticket ??
                  currentEntry.actual_output?.create_ticket)
                    ? "YES"
                    : "NO"
                }
              />
              <Tag
                label="Status"
                value={normalizeReviewStatus(currentEntry.correction_type)}
              />
            </div>
            <Field
              label="Response"
              value={String(
                currentEntry.ideal_output?.response ??
                  currentEntry.actual_output?.response ??
                  ""
              )}
            />
            <Field
              label="Issue summary"
              value={String(
                currentEntry.ideal_output?.issue_summary ??
                  currentEntry.actual_output?.issue_summary ??
                  ""
              )}
            />
          </Section>

          <Section label="Review">
            <Field
              label="Human notes"
              value={currentEntry.human_notes || "-"}
              italic
            />
            <Field
              label="Reasoning"
              value={currentEntry.reasoning || "-"}
              italic
            />
          </Section>
        </div>
      )}

      {editMode && editedEntry && (
        <div className="card overflow-hidden">
          <div className="training-actions training-actions--toolbar">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void saveEdit()}
              disabled={saving}
            >
              Save changes
            </button>
          </div>
          <Section label="Tenant message">
            <div className="training-tenant-msg">{editedEntry.input_text}</div>
          </Section>

          <Section label="Edit response">
            <div className="training-edit-grid">
              <EditSelect
                label="Category"
                value={String(editedEntry.ideal_output?.category ?? "")}
                options={CATEGORIES}
                onChange={(v) =>
                  setEditedEntry({
                    ...editedEntry,
                    ideal_output: { ...editedEntry.ideal_output, category: v },
                  })
                }
              />
              <EditSelect
                label="Priority"
                value={String(editedEntry.ideal_output?.priority ?? "")}
                options={PRIORITIES}
                onChange={(v) =>
                  setEditedEntry({
                    ...editedEntry,
                    ideal_output: { ...editedEntry.ideal_output, priority: v },
                  })
                }
              />
              <EditSelect
                label="Ticket"
                value={String(Boolean(editedEntry.ideal_output?.create_ticket))}
                options={["true", "false"]}
                onChange={(v) =>
                  setEditedEntry({
                    ...editedEntry,
                    ideal_output: {
                      ...editedEntry.ideal_output,
                      create_ticket: v === "true",
                    },
                  })
                }
              />
              <EditSelect
                label="Status"
                value={normalizeReviewStatus(editedEntry.correction_type)}
                options={STATUSES}
                onChange={(v) =>
                  setEditedEntry({ ...editedEntry, correction_type: v as any })
                }
              />
            </div>
            <div className="u-mt-16">
              <label className="training-edit-label">Response</label>
              <textarea
                className="field w-full"
                value={String(editedEntry.ideal_output?.response ?? "")}
                rows={4}
                onChange={(e) =>
                  setEditedEntry({
                    ...editedEntry,
                    ideal_output: {
                      ...editedEntry.ideal_output,
                      response: e.target.value,
                    },
                  })
                }
              />
            </div>
            <div className="u-mt-12">
              <label className="training-edit-label">Issue summary</label>
              <input
                type="text"
                className="field w-full"
                value={String(editedEntry.ideal_output?.issue_summary ?? "")}
                onChange={(e) =>
                  setEditedEntry({
                    ...editedEntry,
                    ideal_output: {
                      ...editedEntry.ideal_output,
                      issue_summary: e.target.value,
                    },
                  })
                }
              />
            </div>
          </Section>

          <Section label="Review notes">
            <div className="u-mb-12">
              <label className="training-edit-label">Human Notes</label>
              <textarea
                className="field w-full"
                value={editedEntry.human_notes || ""}
                rows={3}
                onChange={(e) =>
                  setEditedEntry({
                    ...editedEntry,
                    human_notes: e.target.value,
                  })
                }
              />
            </div>
            <div>
              <label className="training-edit-label">Reasoning</label>
              <textarea
                className="field w-full"
                value={editedEntry.reasoning || ""}
                rows={3}
                onChange={(e) =>
                  setEditedEntry({ ...editedEntry, reasoning: e.target.value })
                }
              />
            </div>
          </Section>

          <div className="training-actions">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void saveEdit()}
              disabled={saving}
            >
              Save changes
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={cancelEdit}
              disabled={saving}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className="training-shortcuts">
        Left/Right or J/K navigate · E edit · A approve · R reject
      </div>
    </section>
  );
}

function Section({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="training-section">
      <div className="training-section-label">{label}</div>
      {children}
    </div>
  );
}

function Tag({ label, value }: { label: string; value: string }) {
  return (
    <div className="training-tag-box">
      <div className="training-tag-label">{label}</div>
      <div className="training-tag-value">{value}</div>
    </div>
  );
}

function Field({
  label,
  value,
  italic,
}: {
  label: string;
  value: string;
  italic?: boolean;
}) {
  return (
    <div className="u-mt-10">
      <div className="training-mini-label">{label}</div>
      <div
        className="training-field-box"
        style={{ fontStyle: italic ? "italic" : "normal" }}
      >
        {value}
      </div>
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
      <label className="training-edit-label">{label}</label>
      <select
        className="field"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    </div>
  );
}
