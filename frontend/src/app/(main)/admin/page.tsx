"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  adminCreateClassificationOverride,
  getTicketById,
  getSession,
  adminCreateResolutionNote,
  adminListClassificationOverrides,
  adminCreateDoc,
  adminDeleteDoc,
  adminGetDoc,
  adminListResolutionNotes,
  adminListKnowledgeGaps,
  adminListDocs,
  adminListUsers,
  adminUpdateUser,
  logout as logoutRequest,
  adminReindex,
  adminUploadDoc,
  adminUpdateDoc,
  type AdminDoc,
  type AdminUserRow,
  type ClassificationOverride,
  type KnowledgeGap,
  type ResolutionNote,
  type Ticket,
} from "../../../lib/api";

const DOC_NAME_REGEX = /^[a-zA-Z0-9._-]+\.(md|txt)$/i;

function formatGapReason(notes: string): { title: string; detail?: string } {
  const n = (notes || "").trim();
  if (!n) return { title: "—" };
  if (n.includes("grounded=NO") && n.includes("informational")) {
    return {
      title: "Missing FM documentation (informational question)",
      detail: n,
    };
  }
  if (n.startsWith("resolved_in=")) {
    return { title: "Resolved into knowledge base", detail: n };
  }
  return { title: "System / audit note", detail: n };
}

type UserEdit = { email: string; role: "admin" | "user"; active: boolean };
type AdminTab = "tickets" | "knowledge" | "users" | "documents";

function priorityBadgeStyle(priority: string): React.CSSProperties {
  const p = (priority || "").toUpperCase();
  if (p === "URGENT") {
    return { border: "1px solid var(--chip-danger-border)", background: "var(--chip-danger-bg)", color: "var(--chip-danger-text)" };
  }
  if (p === "HIGH") {
    return { border: "1px solid var(--chip-warn-border)", background: "var(--chip-warn-bg)", color: "var(--chip-warn-text)" };
  }
  if (p === "LOW") {
    return { border: "1px solid var(--chip-success-border)", background: "var(--chip-success-bg)", color: "var(--chip-success-text)" };
  }
  return { border: "1px solid var(--chip-info-border)", background: "var(--chip-info-bg)", color: "var(--chip-info-text)" };
}

export default function AdminPage() {
  const router = useRouter();
  const [adminUsername, setAdminUsername] = useState("");
  const [adminUserId, setAdminUserId] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  const [docs, setDocs] = useState<AdminDoc[]>([]);
  const [selectedName, setSelectedName] = useState("");
  const [content, setContent] = useState("");
  const [newName, setNewName] = useState("");
  const [newContent, setNewContent] = useState("");
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadOverwrite, setUploadOverwrite] = useState(true);
  const [uploadAutoReindex, setUploadAutoReindex] = useState(true);
  const [status, setStatus] = useState("Sign in and click Load docs.");
  const [busy, setBusy] = useState(false);
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [gapFilter, setGapFilter] = useState<"" | "new" | "reviewed" | "resolved">("");
  const [users, setUsers] = useState<AdminUserRow[]>([]);
  const [userEdits, setUserEdits] = useState<Record<number, UserEdit>>({});
  const [userBusyId, setUserBusyId] = useState<number | null>(null);
  const [opsTicketId, setOpsTicketId] = useState("");
  const [resolutionNote, setResolutionNote] = useState("");
  const [resolutionParts, setResolutionParts] = useState("");
  const [resolutionCost, setResolutionCost] = useState("");
  const [resolutionMinutes, setResolutionMinutes] = useState("");
  const [overrideField, setOverrideField] = useState<"category" | "priority" | "department">("category");
  const [overrideValue, setOverrideValue] = useState("");
  const [opsNotes, setOpsNotes] = useState<ResolutionNote[]>([]);
  const [opsOverrides, setOpsOverrides] = useState<ClassificationOverride[]>([]);
  const [opsTicketPreview, setOpsTicketPreview] = useState<Ticket | null>(null);
  const [activeTab, setActiveTab] = useState<AdminTab>("tickets");

  const hasSelection = useMemo(() => Boolean(selectedName), [selectedName]);
  const hasSession = useMemo(() => Boolean(adminUsername), [adminUsername]);

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") {
          router.replace("/chat");
          return;
        }
        setAdminUsername(res.user.username);
        setAdminUserId(res.user.id);
        setReady(true);
      })
      .catch(() => router.replace("/"));
  }, [router]);

  async function loadUsers({ quiet }: { quiet?: boolean } = {}) {
    if (!hasSession) return;
    if (!quiet) setStatus("Loading users...");
    try {
      const res = await adminListUsers();
      setUsers(res.users);
      const next: Record<number, UserEdit> = {};
      for (const u of res.users) {
        next[u.id] = {
          email: u.email ?? "",
          role: u.role,
          active: Boolean(u.is_active),
        };
      }
      setUserEdits(next);
      if (!quiet) setStatus(`Loaded ${res.users.length} users.`);
    } catch (err) {
      setStatus(`Users load failed: ${(err as Error).message}`);
    }
  }

  useEffect(() => {
    if (!adminUsername) return;
    loadUsers({ quiet: true });
  }, [adminUsername]);

  useEffect(() => {
    if (!hasSession) return;
    if (activeTab === "documents") {
      loadDocs({ quiet: true });
      return;
    }
    if (activeTab === "knowledge") {
      loadGaps({ quiet: true });
      return;
    }
    if (activeTab === "users") {
      loadUsers({ quiet: true });
    }
  }, [hasSession, activeTab, gapFilter]);

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
      await loadGaps({ quiet: true });
    } catch (err) {
      setStatus(`Load failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function loadGaps({ quiet }: { quiet?: boolean } = {}) {
    if (!hasSession) return;
    if (!quiet) setStatus("Loading knowledge gaps...");
    try {
      const res = await adminListKnowledgeGaps(gapFilter || undefined);
      setGaps(res.gaps);
      if (!quiet) setStatus(`Loaded ${res.gaps.length} knowledge gaps.`);
    } catch (err) {
      setStatus(`Knowledge gaps load failed: ${(err as Error).message}`);
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
      setStatus("Name must use only letters/numbers/_/.- and end with .md or .txt");
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
      const res = await adminReindex();
      setStatus(`Reindex complete. Chunks indexed: ${res.chunks_indexed}`);
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
        uploadAutoReindex
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

  async function saveUserRow(userId: number) {
    const edit = userEdits[userId];
    if (!edit || !hasSession) return;
    setUserBusyId(userId);
    setStatus(`Saving user #${userId}...`);
    try {
      await adminUpdateUser(userId, {
        role: edit.role,
        is_active: edit.active,
        email: edit.email.trim() ? edit.email.trim() : null,
      });
      await loadUsers({ quiet: true });
      setStatus(`User #${userId} updated.`);
    } catch (err) {
      setStatus(`User update failed: ${(err as Error).message}`);
    } finally {
      setUserBusyId(null);
    }
  }

  async function logout() {
    await logoutRequest();
    router.replace("/");
  }

  async function loadOpsHistory() {
    const ticketId = Number(opsTicketId);
    if (!hasSession || !Number.isInteger(ticketId) || ticketId <= 0) {
      setStatus("Provide a valid numeric ticket ID.");
      return;
    }
    setBusy(true);
    setStatus(`Loading ops history for ticket #${ticketId}...`);
    try {
      const [ticketRes, notesRes, overridesRes] = await Promise.all([
        getTicketById(ticketId),
        adminListResolutionNotes(ticketId),
        adminListClassificationOverrides(ticketId),
      ]);
      setOpsTicketPreview(ticketRes.ticket);
      setOpsNotes(notesRes.notes);
      setOpsOverrides(overridesRes.overrides);
      setStatus(`Loaded ticket #${ticketId} ops history.`);
    } catch (err) {
      setStatus(`Ops history load failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function submitResolutionNote() {
    const ticketId = Number(opsTicketId);
    if (!hasSession || !Number.isInteger(ticketId) || ticketId <= 0) {
      setStatus("Provide a valid numeric ticket ID.");
      return;
    }
    if (!resolutionNote.trim()) {
      setStatus("Resolution note is required.");
      return;
    }
    setBusy(true);
    setStatus(`Saving resolution note for ticket #${ticketId}...`);
    try {
      await adminCreateResolutionNote(ticketId, {
        note: resolutionNote.trim(),
        parts_used: resolutionParts.trim(),
        cost: resolutionCost.trim() ? Number(resolutionCost) : null,
        time_spent_minutes: resolutionMinutes.trim() ? Number(resolutionMinutes) : null,
      });
      setResolutionNote("");
      setResolutionParts("");
      setResolutionCost("");
      setResolutionMinutes("");
      await loadOpsHistory();
      setStatus(`Resolution note saved for ticket #${ticketId}.`);
    } catch (err) {
      setStatus(`Resolution note save failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function submitClassificationOverride() {
    const ticketId = Number(opsTicketId);
    if (!hasSession || !Number.isInteger(ticketId) || ticketId <= 0) {
      setStatus("Provide a valid numeric ticket ID.");
      return;
    }
    if (!overrideValue.trim()) {
      setStatus("Override value is required.");
      return;
    }
    setBusy(true);
    setStatus(`Saving override for ticket #${ticketId}...`);
    try {
      const res = await adminCreateClassificationOverride(ticketId, {
        field_changed: overrideField,
        manager_value: overrideValue.trim(),
      });
      setOpsTicketPreview(res.ticket);
      setOverrideValue("");
      await loadOpsHistory();
      setStatus(
        `Override saved for ticket #${ticketId}. Training examples updated: ${res.training_examples_updated}.`
      );
    } catch (err) {
      setStatus(`Override save failed: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  if (!ready) {
    return (
      <section>
        <h1>Admin Knowledge Base</h1>
        <p>Checking admin session...</p>
      </section>
    );
  }

  return (
    <section className="page-shell">
      <h1>Admin Knowledge Base</h1>
      <div className="card panel-grid">
        <p style={{ margin: 0 }}>You are logged in as <strong>{adminUsername}</strong>.</p>
        <div className="toolbar">
          <button onClick={() => setActiveTab("tickets")} className={activeTab === "tickets" ? "btn" : "btn btn-ghost"}>
            Tickets Ops
          </button>
          <button onClick={() => setActiveTab("knowledge")} className={activeTab === "knowledge" ? "btn" : "btn btn-ghost"}>
            Knowledge Gaps
          </button>
          <button onClick={() => setActiveTab("users")} className={activeTab === "users" ? "btn" : "btn btn-ghost"}>
            Users
          </button>
          <button onClick={() => setActiveTab("documents")} className={activeTab === "documents" ? "btn" : "btn btn-ghost"}>
            Documents
          </button>
        </div>
      </div>

      {activeTab === "tickets" && <div className="card panel-grid">
        <h3>Ticket Learning Loop (v1.5)</h3>
        <p style={{ margin: 0, color: "var(--muted)" }}>
          Add resolution notes and classification overrides per ticket. Overrides are synced to training examples.
        </p>
        <div className="toolbar">
          <input
            className="field"
            style={{ width: 160 }}
            value={opsTicketId}
            onChange={(e) => setOpsTicketId(e.target.value)}
            placeholder="Ticket ID (e.g. 42)"
          />
          <button onClick={loadOpsHistory} disabled={busy || !hasSession}>
            Load ticket history
          </button>
        </div>
        {opsTicketPreview ? (
          <div
            style={{
              border: "1px solid var(--border)",
              borderRadius: 10,
              padding: 12,
              background: "var(--surface)",
              display: "grid",
              gap: 10,
            }}
          >
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <span
                style={{
                  fontSize: 12,
                  padding: "2px 8px",
                  borderRadius: 999,
                  border: "1px solid var(--border)",
                  background: "var(--surface-2)",
                }}
              >
                Ticket #{opsTicketPreview.id}
              </span>
              <span
                style={{
                  fontSize: 12,
                  padding: "2px 8px",
                  borderRadius: 999,
                  border: "1px solid var(--border)",
                  background: "var(--surface-2)",
                }}
              >
                Status: {opsTicketPreview.status}
              </span>
              <span
                style={{
                  fontSize: 12,
                  padding: "2px 8px",
                  borderRadius: 999,
                  ...priorityBadgeStyle(opsTicketPreview.priority),
                }}
              >
                Priority: {opsTicketPreview.priority}
              </span>
              <span
                style={{
                  fontSize: 12,
                  padding: "2px 8px",
                  borderRadius: 999,
                  border: "1px solid var(--border)",
                  background: "var(--surface-2)",
                }}
              >
                Category: {opsTicketPreview.category}
              </span>
            </div>

            <div style={{ display: "grid", gap: 8 }}>
              <div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>Issue summary</div>
                <div style={{ fontSize: 14 }}>{opsTicketPreview.issue_summary || "—"}</div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>User message</div>
                <div
                  style={{
                    fontSize: 14,
                    background: "var(--surface-inset)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: 8,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {opsTicketPreview.message || "—"}
                </div>
              </div>
              <div>
                <div style={{ fontSize: 12, color: "var(--muted)" }}>Assistant response</div>
                <div
                  style={{
                    fontSize: 14,
                    background: "var(--surface-inset)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: 8,
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {opsTicketPreview.response || "—"}
                </div>
              </div>
              <div style={{ fontSize: 12, color: "var(--muted)" }}>
                Department: {opsTicketPreview.department || "—"}
              </div>
            </div>
          </div>
        ) : null}
        <div className="split-layout">
          <div className="card panel-grid">
            <h4 style={{ margin: 0 }}>Resolution Note</h4>
            <textarea
              className="field"
              rows={4}
              value={resolutionNote}
              onChange={(e) => setResolutionNote(e.target.value)}
              placeholder="What was done to resolve the issue?"
            />
            <input
              className="field"
              value={resolutionParts}
              onChange={(e) => setResolutionParts(e.target.value)}
              placeholder="Parts used (optional)"
            />
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="field"
                value={resolutionCost}
                onChange={(e) => setResolutionCost(e.target.value)}
                placeholder="Cost (optional)"
              />
              <input
                className="field"
                value={resolutionMinutes}
                onChange={(e) => setResolutionMinutes(e.target.value)}
                placeholder="Time spent min (optional)"
              />
            </div>
            <button onClick={submitResolutionNote} disabled={busy || !hasSession}>
              Save resolution note
            </button>
          </div>
          <div className="card panel-grid">
            <h4 style={{ margin: 0 }}>Classification Override</h4>
            <div style={{ display: "flex", gap: 8 }}>
              <select
                className="field"
                value={overrideField}
                onChange={(e) =>
                  setOverrideField(e.target.value as "category" | "priority" | "department")
                }
              >
                <option value="category">category</option>
                <option value="priority">priority</option>
                <option value="department">department</option>
              </select>
              <input
                className="field"
                value={overrideValue}
                onChange={(e) => setOverrideValue(e.target.value)}
                placeholder="New manager value"
              />
            </div>
            <button onClick={submitClassificationOverride} disabled={busy || !hasSession}>
              Save override
            </button>
          </div>
        </div>
        <div className="split-layout">
          <div className="card panel-grid">
            <h4 style={{ margin: 0 }}>Resolution Notes History</h4>
            <div style={{ maxHeight: 220, overflowY: "auto" }}>
              {opsNotes.length === 0 ? (
                <p style={{ margin: 0, color: "var(--muted)" }}>No notes loaded.</p>
              ) : (
                opsNotes.map((n) => (
                  <div key={n.id} style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      #{n.id} by {n.added_by || "admin"} at {new Date(n.created_at).toLocaleString()}
                    </div>
                    <div>{n.note}</div>
                    {(n.parts_used || n.time_spent_minutes || n.cost !== null) && (
                      <div style={{ fontSize: 12, color: "var(--muted)" }}>
                        {n.parts_used ? `parts: ${n.parts_used}` : ""}
                        {n.time_spent_minutes ? ` | minutes: ${n.time_spent_minutes}` : ""}
                        {n.cost !== null ? ` | cost: ${n.cost}` : ""}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="card panel-grid">
            <h4 style={{ margin: 0 }}>Classification Override History</h4>
            <div style={{ maxHeight: 220, overflowY: "auto" }}>
              {opsOverrides.length === 0 ? (
                <p style={{ margin: 0, color: "var(--muted)" }}>No overrides loaded.</p>
              ) : (
                opsOverrides.map((o) => (
                  <div key={o.id} style={{ borderBottom: "1px solid var(--border)", padding: "8px 0" }}>
                    <div style={{ fontSize: 12, color: "var(--muted)" }}>
                      #{o.id} by {o.changed_by || "admin"} at {new Date(o.created_at).toLocaleString()}
                    </div>
                    <div>
                      {o.field_changed}: <strong>{o.ai_value || "—"}</strong> →{" "}
                      <strong>{o.manager_value}</strong>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>}

      {activeTab === "users" && <div className="card panel-grid">
        <h3>Users</h3>
        <p style={{ margin: 0, color: "var(--muted)" }}>
          Set roles, active flag, and optional email (for ticket status notifications). At least one active admin is required.
        </p>
        <div className="toolbar">
          <button type="button" onClick={() => loadUsers()} disabled={busy || !hasSession}>
            Refresh users
          </button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th align="left">ID</th>
                <th align="left">Username</th>
                <th align="left">Email</th>
                <th align="left">Role</th>
                <th align="left">Active</th>
                <th align="left">Action</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => {
                const edit = userEdits[u.id];
                const self = adminUserId === u.id;
                return (
                  <tr key={u.id}>
                    <td>{u.id}</td>
                    <td>{u.username}</td>
                    <td>
                      <input
                        className="field"
                        style={{ minWidth: 180 }}
                        value={edit?.email ?? ""}
                        onChange={(e) =>
                          setUserEdits((prev) => ({
                            ...prev,
                            [u.id]: { ...(prev[u.id] ?? { email: "", role: u.role, active: !!u.is_active }), email: e.target.value },
                          }))
                        }
                        placeholder="optional"
                      />
                    </td>
                    <td>
                      <select
                        className="field"
                        style={{ width: 120 }}
                        value={edit?.role ?? u.role}
                        onChange={(e) =>
                          setUserEdits((prev) => ({
                            ...prev,
                            [u.id]: {
                              ...(prev[u.id] ?? { email: u.email ?? "", role: u.role, active: !!u.is_active }),
                              role: e.target.value as "admin" | "user",
                            },
                          }))
                        }
                      >
                        <option value="user">user</option>
                        <option value="admin">admin</option>
                      </select>
                    </td>
                    <td>
                      <input
                        type="checkbox"
                        checked={edit?.active ?? !!u.is_active}
                        disabled={self}
                        title={self ? "Use another admin to deactivate this account" : undefined}
                        onChange={(e) =>
                          setUserEdits((prev) => ({
                            ...prev,
                            [u.id]: {
                              ...(prev[u.id] ?? { email: u.email ?? "", role: u.role, active: !!u.is_active }),
                              active: e.target.checked,
                            },
                          }))
                        }
                      />
                    </td>
                    <td>
                      <button
                        type="button"
                        onClick={() => saveUserRow(u.id)}
                        disabled={userBusyId !== null || !hasSession}
                      >
                        {userBusyId === u.id ? "Saving..." : "Save"}
                      </button>
                    </td>
                  </tr>
                );
              })}
              {users.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ color: "var(--muted)" }}>
                    No users loaded.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>}

      {activeTab === "knowledge" && <div className="card panel-grid">
        <h3>Knowledge Gaps</h3>
        <div className="toolbar">
          <select
            className="field"
            style={{ width: 180 }}
            value={gapFilter}
            onChange={(e) =>
              setGapFilter(e.target.value as "" | "new" | "reviewed" | "resolved")
            }
          >
            <option value="">All statuses</option>
            <option value="new">new</option>
            <option value="reviewed">reviewed</option>
            <option value="resolved">resolved</option>
          </select>
          <button onClick={() => loadGaps()} disabled={busy || !hasSession}>
            Refresh gaps
          </button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th align="left">ID</th>
                <th align="left">Question</th>
                <th align="left">Ticket</th>
                <th align="left">Category</th>
                <th align="left">Status</th>
                <th align="left">Reason</th>
                <th align="left">Created</th>
                <th align="left">Action</th>
              </tr>
            </thead>
            <tbody>
              {gaps.map((g) => (
                <tr key={g.id}>
                  <td>{g.id}</td>
                  <td>{g.question}</td>
                  <td>{g.ticket_id ?? "-"}</td>
                  <td>{g.category}</td>
                  <td>{g.status}</td>
                  <td style={{ maxWidth: 300, verticalAlign: "top" }}>
                    {(() => {
                      const r = formatGapReason(g.notes || "");
                      return (
                        <>
                          <span className="knowledge-gap-reason-title">{r.title}</span>
                          {r.detail ? (
                            <span className="knowledge-gap-reason-detail">{r.detail}</span>
                          ) : null}
                        </>
                      );
                    })()}
                  </td>
                  <td>{new Date(g.created_at).toLocaleString()}</td>
                  <td style={{ display: "flex", gap: 6 }}>
                    <button
                      onClick={() => router.push(`/admin/gaps/${g.id}`)}
                      disabled={busy || g.status === "resolved"}
                    >
                      Resolve...
                    </button>
                  </td>
                </tr>
              ))}
              {gaps.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-muted">
                    No knowledge gaps found for current filter.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>}

      {activeTab === "documents" && <>
        <div className="card panel-grid">
          <div className="toolbar">
            <button onClick={() => loadDocs()} disabled={busy || !hasSession}>
              Refresh docs
            </button>
            <button onClick={runReindex} disabled={busy || !hasSession}>
              Reindex
            </button>
          </div>
        </div>
        <div className="split-layout">
          <div className="card">
            <h3>Documents</h3>
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
            <h3>Editor {selectedName ? `- ${selectedName}` : ""}</h3>
            <textarea
              value={content}
              onChange={(e) => setContent(e.target.value)}
              rows={16}
            style={{ width: "100%" }}
            className="field"
              placeholder="Select a document to edit..."
            />
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={saveDoc} disabled={busy || !hasSelection}>
                Save
              </button>
              <button onClick={deleteDoc} disabled={busy || !hasSelection || !hasSession}>
                Delete
              </button>
            </div>
          </div>
        </div>

        <div className="card panel-grid">
          <h3>Create New Document</h3>
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="e.g. elevator_maintenance.md"
            className="field"
          />
          <textarea
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            rows={8}
            placeholder="New document content..."
            className="field"
          />
          <button onClick={createDoc} disabled={busy || !hasSession}>
            Create document
          </button>
        </div>

        <div className="card panel-grid">
          <h3>Upload Document</h3>
          <p className="text-muted" style={{ margin: 0 }}>
            Supported: .txt, .md, .csv, .pdf, .docx
          </p>
          <input
            type="file"
            onChange={(e) => setUploadFile(e.target.files?.[0] ?? null)}
            accept=".txt,.md,.csv,.pdf,.docx"
          />
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={uploadOverwrite}
              onChange={(e) => setUploadOverwrite(e.target.checked)}
            />
            Overwrite if converted target already exists
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={uploadAutoReindex}
              onChange={(e) => setUploadAutoReindex(e.target.checked)}
            />
            Auto reindex right after upload
          </label>
          <button onClick={uploadDoc} disabled={busy || !hasSession || !uploadFile}>
            Upload file
          </button>
        </div>
      </>}

      <p style={{ marginTop: 12 }}>{status}</p>
    </section>
  );
}
