"use client";

import { useEffect, useMemo, useState } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import {
  adminCreateDoc,
  adminDeleteDoc,
  adminGetDoc,
  adminListDocs,
  adminPatchRagSettings,
  adminReindex,
  adminReindexDefaults,
  adminUpdateDoc,
  adminUploadDoc,
  getSession,
  type AdminDoc,
  type IngestPreChunkOptions,
} from "../../lib/api";
import { DOC_NAME_REGEX } from "../../lib/adminShared";

export function AdminDocumentsPanel() {
  const { locale, t } = useI18n();
  const tr = (en: string, nl: string) => (locale === "nl" ? nl : en);
  const [adminUsername, setAdminUsername] = useState("");
  const [docs, setDocs] = useState<AdminDoc[]>([]);
  const [selectedName, setSelectedName] = useState("");
  const [content, setContent] = useState("");
  const [newName, setNewName] = useState("");
  const [newContent, setNewContent] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadOverwrite, setUploadOverwrite] = useState(true);
  const [uploadAutoReindex, setUploadAutoReindex] = useState(true);
  const [ingestChunkSize, setIngestChunkSize] = useState(1200);
  const [ingestChunkOverlap, setIngestChunkOverlap] = useState(150);
  const [ragTopK, setRagTopK] = useState(3);
  const [ragTopKEnvDefault, setRagTopKEnvDefault] = useState<number | null>(null);
  const [ragTopKMetaOverride, setRagTopKMetaOverride] = useState(false);
  const [ragTopKLimits, setRagTopKLimits] = useState<{ min: number; max: number } | null>(
    null
  );
  const [ingestPreChunk, setIngestPreChunk] = useState<IngestPreChunkOptions | null>(
    null
  );
  const [chunkLimits, setChunkLimits] = useState<{
    chunk_size_min: number;
    chunk_size_max: number;
  } | null>(null);
  const [status, setStatus] = useState(
    tr("Sign in and click refresh.", "Log in en klik op vernieuwen.")
  );
  const [busy, setBusy] = useState(false);

  const hasSelection = useMemo(() => Boolean(selectedName), [selectedName]);
  const hasSession = Boolean(adminUsername);

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") return;
        setAdminUsername(res.user.username);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!hasSession) return;
    void loadDocs({ quiet: true });
  }, [hasSession]);

  async function loadRagAndIngestDefaults() {
    const d = await adminReindexDefaults();
    setIngestChunkSize(d.ingest_chunk_size);
    setIngestChunkOverlap(d.ingest_chunk_overlap);
    setRagTopK(d.rag_top_k);
    setRagTopKEnvDefault(d.rag_top_k_env_startup_default);
    setRagTopKMetaOverride(d.rag_top_k_meta_override_active);
    setRagTopKLimits(d.rag_top_k_limits);
    setIngestPreChunk(d.ingest_pre_chunk);
    setChunkLimits({
      chunk_size_min: d.limits.chunk_size_min,
      chunk_size_max: d.limits.chunk_size_max,
    });
  }

  useEffect(() => {
    if (!hasSession) return;
    void loadRagAndIngestDefaults().catch(() => {});
  }, [hasSession]);

  async function saveRagTopK() {
    if (!hasSession) return;
    setBusy(true);
    setStatus(t("adminSettings.ragTopKSaving"));
    try {
      await adminPatchRagSettings({ rag_top_k: ragTopK });
      await loadRagAndIngestDefaults();
      setStatus(t("adminSettings.ragTopKSaved"));
    } catch (err) {
      setStatus(`${t("adminSettings.ragTopKSaveFailed")}: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function clearRagTopKOverride() {
    if (!hasSession) return;
    setBusy(true);
    setStatus(t("adminSettings.ragTopKClearing"));
    try {
      await adminPatchRagSettings({ clear_rag_top_k_override: true });
      await loadRagAndIngestDefaults();
      setStatus(t("adminSettings.ragTopKCleared"));
    } catch (err) {
      setStatus(`${t("adminSettings.ragTopKClearFailed")}: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function loadDocs({ quiet }: { quiet?: boolean } = {}) {
    if (!hasSession) {
      setStatus("Admin session missing.");
      return;
    }
    setBusy(true);
    if (!quiet) setStatus("Loading documents...");
    try {
      const res = await adminListDocs();
      setDocs(res.docs);
      if (!quiet) setStatus(`Loaded ${res.docs.length} documents.`);
      if (res.docs.length && !selectedName) {
        await openDoc(res.docs[0].name);
      }
    } catch (err) {
      setStatus(`Load failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function openDoc(name: string) {
    if (!hasSession) {
      setStatus("Admin session missing.");
      return;
    }
    setBusy(true);
    setStatus(`Opening ${name}...`);
    try {
      const res = await adminGetDoc(name);
      setSelectedName(res.name);
      setContent(res.content);
      setStatus(`Opened ${res.name}.`);
    } catch (err) {
      setStatus(`Open failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function saveDoc() {
    if (!hasSelection) return;
    if (!hasSession) {
      setStatus("Admin session missing.");
      return;
    }
    setBusy(true);
    setStatus(`Saving ${selectedName}...`);
    try {
      await adminUpdateDoc(selectedName, content);
      setStatus(`Saved ${selectedName}.`);
      await loadDocs({ quiet: true });
    } catch (err) {
      setStatus(`Save failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function createDoc() {
    if (!hasSession) {
      setStatus("Admin session missing.");
      return;
    }
    if (!newName.trim()) {
      setStatus("New doc name is required.");
      return;
    }
    if (!DOC_NAME_REGEX.test(newName.trim())) {
      setStatus(
        "Name must use only letters/numbers/_/.- and end with .md or .txt"
      );
      return;
    }
    setBusy(true);
    setStatus(`Creating ${newName}...`);
    try {
      await adminCreateDoc(newName.trim(), newContent);
      setNewName("");
      setNewContent("");
      setStatus("Document created.");
      await loadDocs({ quiet: true });
    } catch (err) {
      setStatus(`Create failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function deleteDoc() {
    if (!hasSelection) return;
    if (!hasSession) {
      setStatus("Admin session missing.");
      return;
    }
    if (!window.confirm(`Delete ${selectedName}?`)) return;
    setBusy(true);
    setStatus(`Deleting ${selectedName}...`);
    try {
      await adminDeleteDoc(selectedName);
      setSelectedName("");
      setContent("");
      setStatus("Document deleted.");
      await loadDocs({ quiet: true });
    } catch (err) {
      setStatus(`Delete failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function runReindex() {
    if (!hasSession) {
      setStatus("Admin session missing.");
      return;
    }
    setBusy(true);
    setStatus("Reindexing docs...");
    try {
      const res = await adminReindex({
        chunk_size: ingestChunkSize,
        chunk_overlap: ingestChunkOverlap,
      });
      setStatus(
        `Reindex complete. Chunks indexed: ${res.chunks_indexed} (size ${res.chunk_size}, overlap ${res.chunk_overlap})`
      );
    } catch (err) {
      setStatus(`Reindex failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function uploadDoc() {
    if (!hasSession) {
      setStatus("Admin session missing.");
      return;
    }
    if (!uploadFile) {
      setStatus("Choose a file to upload first.");
      return;
    }
    setBusy(true);
    setStatus(`Uploading ${uploadFile.name}...`);
    try {
      const res = await adminUploadDoc(
        uploadFile,
        uploadOverwrite,
        uploadAutoReindex,
        uploadAutoReindex
          ? {
              chunk_size: ingestChunkSize,
              chunk_overlap: ingestChunkOverlap,
            }
          : undefined
      );
      const reindexMsg =
        res.auto_reindexed && res.chunks_indexed !== null
          ? ` Auto reindex done (${res.chunks_indexed} chunks).`
          : "";
      const finalStatus = `Uploaded ${res.source_filename} as ${res.saved_as} (${res.chars} chars).${reindexMsg}`;
      setUploadFile(null);
      await loadDocs({ quiet: true });
      setStatus(finalStatus);
    } catch (err) {
      setStatus(`Upload failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <div className="card panel-grid">
        <p className="text-muted m-0" style={{ maxWidth: "52rem" }}>
          {t("adminSettings.ingestChunkHelp")}
        </p>
        <div
          className="toolbar"
          style={{ flexWrap: "wrap", alignItems: "flex-end", gap: 12 }}
        >
          <label className="m-0" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span>{t("adminSettings.ingestChunkSize")}</span>
            <input
              type="number"
              className="field"
              style={{ width: "8rem" }}
              min={chunkLimits?.chunk_size_min ?? 200}
              max={chunkLimits?.chunk_size_max ?? 8000}
              value={ingestChunkSize}
              onChange={(e) => setIngestChunkSize(Number(e.target.value))}
              disabled={busy || !hasSession}
            />
          </label>
          <label className="m-0" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span>{t("adminSettings.ingestChunkOverlap")}</span>
            <input
              type="number"
              className="field"
              style={{ width: "8rem" }}
              min={0}
              max={Math.max(0, ingestChunkSize - 1)}
              value={ingestChunkOverlap}
              onChange={(e) => setIngestChunkOverlap(Number(e.target.value))}
              disabled={busy || !hasSession}
            />
          </label>
          <label className="m-0" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            <span>{t("adminSettings.ragTopKLabel")}</span>
            <input
              type="number"
              className="field"
              style={{ width: "8rem" }}
              min={ragTopKLimits?.min ?? 1}
              max={ragTopKLimits?.max ?? 24}
              value={ragTopK}
              onChange={(e) => setRagTopK(Number(e.target.value))}
              disabled={busy || !hasSession}
            />
          </label>
          <button type="button" onClick={() => void saveRagTopK()} disabled={busy || !hasSession}>
            {t("adminSettings.ragTopKApply")}
          </button>
          <button
            type="button"
            onClick={() => void clearRagTopKOverride()}
            disabled={busy || !hasSession || !ragTopKMetaOverride}
          >
            {t("adminSettings.ragTopKResetEnv")}
          </button>
          {ragTopKEnvDefault !== null ? (
            <p className="m-0 text-muted" style={{ alignSelf: "center", maxWidth: "14rem" }}>
              {t("adminSettings.ragTopKEnvFallback")}: {ragTopKEnvDefault}
              {ragTopKMetaOverride ? ` · ${t("adminSettings.ragTopKDbOverrideOn")}` : ""}
            </p>
          ) : null}
          <button onClick={() => loadDocs()} disabled={busy || !hasSession}>
            {t("adminSettings.refresh")} {tr("docs", "documenten")}
          </button>
          <button onClick={runReindex} disabled={busy || !hasSession}>
            {t("adminSettings.reindex")}
          </button>
        </div>
        {ingestPreChunk ? (
          <details className="u-mt-8">
            <summary>{t("adminSettings.ingestPreChunkTitle")}</summary>
            <dl className="admin-kv" style={{ marginTop: 8 }}>
              <dt>{t("adminSettings.ingestPreChunkDocsDir")}</dt>
              <dd>
                <code>{ingestPreChunk.docs_dir}</code>
              </dd>
              <dt>{t("adminSettings.ingestPreChunkChromaDir")}</dt>
              <dd>
                <code>{ingestPreChunk.chroma_dir}</code>
              </dd>
              <dt>{t("adminSettings.ingestPreChunkSanitize")}</dt>
              <dd>{ingestPreChunk.sanitize_instruction_like ? "true" : "false"}</dd>
              <dt>{t("adminSettings.ingestPreChunkSeparators")}</dt>
              <dd>
                <code style={{ whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                  {JSON.stringify(ingestPreChunk.text_splitter_separators)}
                </code>
              </dd>
              <dt>{t("adminSettings.ingestPreChunkKeywordLimit")}</dt>
              <dd>{ingestPreChunk.chunk_metadata_keyword_limit}</dd>
              <dt>{t("adminSettings.ingestPreChunkCollection")}</dt>
              <dd>
                <code>{ingestPreChunk.chroma_collection}</code>
              </dd>
              <dt>{t("adminSettings.ingestPreChunkEmbedInput")}</dt>
              <dd>
                <code>{ingestPreChunk.embed_input_type_for_passages}</code>
              </dd>
            </dl>
            <p className="text-muted m-0" style={{ maxWidth: "48rem" }}>
              {t("adminSettings.ingestPreChunkFootnote")}
            </p>
          </details>
        ) : null}
      </div>
      <div className="split-layout">
        <div className="card">
          <h3>{t("adminSettings.tabsDocuments")}</h3>
          <div className="admin-doc-list">
            {docs.map((d) => (
              <button
                key={d.name}
                type="button"
                onClick={() => openDoc(d.name)}
                disabled={busy || !hasSession}
                className={`admin-doc-list__item${d.name === selectedName ? " admin-doc-list__item--active" : ""}`}
              >
                {d.name}
              </button>
            ))}
          </div>
        </div>

        <div className="card panel-grid">
          <h3>
            {tr("Editor", "Editor")} {selectedName ? `- ${selectedName}` : ""}
          </h3>
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={16}
            className="field w-full"
            placeholder={tr(
              "Select a document to edit...",
              "Selecteer een document om te bewerken..."
            )}
          />
          <div style={{ display: "flex", gap: 8 }}>
            <button onClick={saveDoc} disabled={busy || !hasSelection}>
              {t("adminSettings.save")}
            </button>
            <button
              onClick={deleteDoc}
              disabled={busy || !hasSelection || !hasSession}
            >
              {t("adminSettings.delete")}
            </button>
          </div>
        </div>
      </div>

      <div className="card panel-grid">
        <h3>{tr("Create New Document", "Nieuw document maken")}</h3>
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder={tr(
            "e.g. elevator_maintenance.md",
            "bijv. elevator_maintenance.md"
          )}
          className="field"
        />
        <textarea
          value={newContent}
          onChange={(e) => setNewContent(e.target.value)}
          rows={8}
          placeholder={tr(
            "New document content...",
            "Nieuwe documentinhoud..."
          )}
          className="field"
        />
        <button onClick={createDoc} disabled={busy || !hasSession}>
          {t("adminSettings.createDocument")}
        </button>
      </div>

      <div className="card panel-grid">
        <h3>{tr("Upload Document", "Document uploaden")}</h3>
        <p className="text-muted m-0">
          {tr("Supported:", "Ondersteund:")} .txt, .md, .csv, .pdf, .docx
        </p>
        <input
          type="file"
          onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
          accept=".txt,.md,.csv,.pdf,.docx"
        />
        <label className="label-inline">
          <input
            type="checkbox"
            checked={uploadOverwrite}
            onChange={(e) => setUploadOverwrite(e.target.checked)}
          />
          {tr(
            "Overwrite if converted target already exists",
            "Overschrijven als geconverteerd doel al bestaat"
          )}
        </label>
        <label className="label-inline">
          <input
            type="checkbox"
            checked={uploadAutoReindex}
            onChange={(e) => setUploadAutoReindex(e.target.checked)}
          />
          {tr(
            "Auto reindex right after upload",
            "Automatisch herindexeren na upload"
          )}
        </label>
        <button
          onClick={uploadDoc}
          disabled={busy || !hasSession || !uploadFile}
        >
          {t("adminSettings.uploadFile")}
        </button>
      </div>

      <p className="u-mt-12">{status}</p>
    </>
  );
}
