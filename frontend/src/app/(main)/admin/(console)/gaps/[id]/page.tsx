"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  adminGetDoc,
  adminGetKnowledgeGap,
  adminListDocs,
  adminResolveKnowledgeGap,
  getSession,
  type AdminDoc,
  type KnowledgeGap,
} from "../../../../../../lib/api";

const CATEGORY_OPTIONS = [
  "HVAC",
  "Electrical",
  "Plumbing",
  "Safety",
  "General",
];
const DOC_NAME_REGEX = /^[a-zA-Z0-9._-]+\.(md|txt)$/i;

export default function ResolveGapPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const gapId = Number(params.id);

  const [gap, setGap] = useState<KnowledgeGap | null>(null);
  const [docs, setDocs] = useState<AdminDoc[]>([]);
  const [docName, setDocName] = useState("fm_updates.md");
  const [useCustomDocName, setUseCustomDocName] = useState(false);
  const [category, setCategory] = useState("General");
  const [useCustomCategory, setUseCustomCategory] = useState(false);
  const [content, setContent] = useState("");
  const [mode, setMode] = useState<"append" | "overwrite">("append");
  const [autoReindex, setAutoReindex] = useState(true);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("Loading knowledge gap...");
  const [loadingDocContent, setLoadingDocContent] = useState(false);

  const customDocAllowed = mode === "append" || docs.length === 0;

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") {
          router.replace("/chat");
          return;
        }
        loadGap();
      })
      .catch(() => router.replace("/"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gapId]);

  useEffect(() => {
    if (customDocAllowed) return;
    setUseCustomDocName(false);
    if (docs.length > 0 && !docs.some((d) => d.name === docName)) {
      setDocName(docs[0].name);
    }
  }, [customDocAllowed, docs, docName]);

  async function loadGap() {
    if (!gapId) return;
    try {
      const [gapRes, docsRes] = await Promise.all([
        adminGetKnowledgeGap(gapId),
        adminListDocs(),
      ]);
      setGap(gapRes.gap);
      setCategory(gapRes.gap.category || "General");
      setDocs(docsRes.docs);
      if (docsRes.docs.length > 0) {
        setDocName(docsRes.docs[0].name);
      }
      setContent(
        `## Knowledge gap: ${gapRes.gap.question}\n\n` +
          `Add missing FM details here.\n`
      );
      setStatus("Gap loaded.");
    } catch (err) {
      setStatus(`Load failed: ${(err as Error).message}`);
    }
  }

  async function loadDocContentForEditing(name: string) {
    if (!name.trim()) return;
    setLoadingDocContent(true);
    setStatus(`Loading content from ${name}...`);
    try {
      const res = await adminGetDoc(name);
      setContent(res.content);
      setStatus(`Loaded ${name}. You can edit and save it.`);
    } catch (err) {
      setStatus(`Failed to load document content: ${(err as Error).message}`);
    } finally {
      setLoadingDocContent(false);
    }
  }

  async function resolveGap() {
    if (!gap) return;
    const normalizedDocName = docName.trim();
    if (!DOC_NAME_REGEX.test(normalizedDocName)) {
      setStatus(
        "Document name must use only letters/numbers/_/.- and end with .md or .txt"
      );
      return;
    }
    const normalizedCategory = category.trim();
    if (!normalizedCategory) {
      setStatus("Category is required.");
      return;
    }
    if (!docName.trim()) {
      setStatus("Document name is required.");
      return;
    }
    if (!content.trim()) {
      setStatus("Content is required.");
      return;
    }
    setBusy(true);
    setStatus(`Resolving gap #${gap.id}...`);
    try {
      const res = await adminResolveKnowledgeGap(gap.id, {
        doc_name: normalizedDocName,
        category: normalizedCategory,
        content,
        mode,
        auto_reindex: autoReindex,
      });
      const reindexMsg =
        res.chunks_indexed !== null
          ? ` Reindexed ${res.chunks_indexed} chunks.`
          : "";
      setStatus(`Resolved in ${res.saved_doc}.${reindexMsg}`);
      setTimeout(() => router.push("/admin/knowledge/gaps"), 1000);
    } catch (err) {
      setStatus(`Resolve failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    if (mode !== "overwrite") return;
    if (useCustomDocName) return;
    if (!docName.trim()) return;
    void loadDocContentForEditing(docName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode, docName, useCustomDocName]);

  return (
    <section className="page-shell">
      <h1>Resolve Knowledge Gap</h1>
      <div className="card panel-grid">
        <p className="m-0">
          <strong>ID:</strong> {gap?.id ?? "-"}
        </p>
        <p className="m-0">
          <strong>Question:</strong> {gap?.question ?? "-"}
        </p>
        <p className="m-0">
          <strong>Current status:</strong> {gap?.status ?? "-"}
        </p>
      </div>

      <div className="card panel-grid">
        <label htmlFor="category">Category</label>
        {!useCustomCategory ? (
          <select
            id="category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        ) : (
          <input
            id="category"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="e.g. Fire Systems, Elevators, BMS"
          />
        )}
        <label className="label-inline">
          <input
            type="checkbox"
            checked={useCustomCategory}
            onChange={(e) => setUseCustomCategory(e.target.checked)}
          />
          Use custom category (create new)
        </label>

        <label htmlFor="doc-name">Target doc name (.md/.txt)</label>
        {!useCustomDocName || !customDocAllowed ? (
          <select
            id="doc-name"
            value={docName}
            onChange={(e) => setDocName(e.target.value)}
          >
            {docs.map((d) => (
              <option key={d.name} value={d.name}>
                {d.name}
              </option>
            ))}
            {docs.length === 0 ? (
              <option value="fm_updates.md">fm_updates.md</option>
            ) : null}
          </select>
        ) : (
          <input
            id="doc-name"
            value={docName}
            onChange={(e) => setDocName(e.target.value)}
            placeholder="e.g. boilers_inventory.md"
          />
        )}
        <label className="label-inline">
          <input
            type="checkbox"
            checked={useCustomDocName}
            onChange={(e) => setUseCustomDocName(e.target.checked)}
            disabled={!customDocAllowed}
          />
          Use custom doc name (create new document)
        </label>
        {mode === "overwrite" && docs.length > 0 ? (
          <p className="text-muted m-0">
            Update mode: select existing doc above, then edit its current text
            in editor below.
          </p>
        ) : null}
        {!customDocAllowed ? (
          <p className="text-muted m-0">
            Custom doc name is available in append mode. Switch to append to
            create a new file.
          </p>
        ) : null}

        <label htmlFor="resolve-content">Content to save</label>
        {mode === "overwrite" ? (
          <p className="text-muted m-0">
            Current content is auto-loaded for editing.
          </p>
        ) : null}
        <textarea
          id="resolve-content"
          rows={14}
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />

        <label htmlFor="mode">Save mode</label>
        <select
          id="mode"
          value={mode}
          onChange={(e) => setMode(e.target.value as "append" | "overwrite")}
        >
          <option value="append">append (add below existing text)</option>
          <option value="overwrite">
            update existing document (edit full text)
          </option>
        </select>

        <label className="label-inline">
          <input
            type="checkbox"
            checked={autoReindex}
            onChange={(e) => setAutoReindex(e.target.checked)}
          />
          Auto reindex after resolve
        </label>

        <div className="flex-gap-8">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={resolveGap}
            disabled={busy || !gap || loadingDocContent}
          >
            Resolve & Save to KB
          </button>
          <button
            type="button"
            onClick={() => router.push("/admin/knowledge/gaps")}
            disabled={busy}
            className="btn btn-ghost"
          >
            Back
          </button>
        </div>
      </div>

      <p className="rag-mt m-0">{status}</p>
    </section>
  );
}
