"use client";

import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import {
  adminCreateClassificationOverride,
  adminCreateResolutionNote,
  adminListClassificationOverrides,
  adminListResolutionNotes,
  getTicketById,
  getSession,
  type ClassificationOverride,
  type ResolutionNote,
  type Ticket,
} from "../../lib/api";
import { priorityBadgeStyle } from "../../lib/adminShared";

export function AdminTicketsPanel() {
  const { locale, t } = useI18n();
  const tr = (en: string, nl: string) => (locale === "nl" ? nl : en);
  const [adminUsername, setAdminUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [opsTicketId, setOpsTicketId] = useState("");
  const [resolutionNote, setResolutionNote] = useState("");
  const [resolutionParts, setResolutionParts] = useState("");
  const [resolutionCost, setResolutionCost] = useState("");
  const [resolutionMinutes, setResolutionMinutes] = useState("");
  const [overrideField, setOverrideField] = useState<
    "category" | "priority" | "department"
  >("category");
  const [overrideValue, setOverrideValue] = useState("");
  const [opsNotes, setOpsNotes] = useState<ResolutionNote[]>([]);
  const [opsOverrides, setOpsOverrides] = useState<ClassificationOverride[]>(
    []
  );
  const [opsTicketPreview, setOpsTicketPreview] = useState<Ticket | null>(null);
  const [status, setStatus] = useState(
    tr("Sign in and load a ticket.", "Log in en laad een ticket.")
  );

  const hasSession = Boolean(adminUsername);

  useEffect(() => {
    getSession()
      .then((res) => {
        if (res.user.role !== "admin") return;
        setAdminUsername(res.user.username);
      })
      .catch(() => {});
  }, []);

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
        time_spent_minutes: resolutionMinutes.trim()
          ? Number(resolutionMinutes)
          : null,
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

  return (
    <>
      <div className="card panel-grid">
        <h3>{tr("Ticket Learning Loop (v1.5)", "Ticket leerlus (v1.5)")}</h3>
        <p className="text-muted m-0">
          {tr(
            "Add resolution notes and classification overrides per ticket. Overrides are synced to training examples.",
            "Voeg per ticket afhandelnotities en classificatie-overschrijvingen toe. Overrides worden gesynchroniseerd met trainingsvoorbeelden."
          )}
        </p>
        <div className="toolbar">
          <input
            className="field field-w-160"
            value={opsTicketId}
            onChange={(e) => setOpsTicketId(e.target.value)}
            placeholder={tr("Ticket ID (e.g. 42)", "Ticket-ID (bijv. 42)")}
          />
          <button onClick={loadOpsHistory} disabled={busy || !hasSession}>
            Load ticket history
          </button>
        </div>
        {opsTicketPreview ? (
          <div className="card tq-grid-10">
            <div className="flex-gap-8-wrap">
              <span className="admin-ticket-chip">
                {tr("Ticket", "Ticket")} #{opsTicketPreview.id}
              </span>
              <span className="admin-ticket-chip">
                {tr("Status", "Status")}: {opsTicketPreview.status}
              </span>
              <span
                className="admin-ticket-chip"
                style={priorityBadgeStyle(opsTicketPreview.priority)}
              >
                {tr("Priority", "Prioriteit")}: {opsTicketPreview.priority}
              </span>
              <span className="admin-ticket-chip">
                {tr("Category", "Categorie")}: {opsTicketPreview.category}
              </span>
            </div>

            <div className="tq-grid-8">
              <div>
                <div className="admin-meta-label">
                  {tr("Issue summary", "Probleemsamenvatting")}
                </div>
                <div className="text-14">
                  {opsTicketPreview.issue_summary || "—"}
                </div>
              </div>
              <div>
                <div className="admin-meta-label">
                  {tr("User message", "Gebruikersbericht")}
                </div>
                <div className="admin-message-box">
                  {opsTicketPreview.message || "—"}
                </div>
              </div>
              <div>
                <div className="admin-meta-label">
                  {tr("Assistant response", "Assistentantwoord")}
                </div>
                <div className="admin-message-box">
                  {opsTicketPreview.response || "—"}
                </div>
              </div>
              <div className="admin-meta-label">
                {tr("Department", "Afdeling")}:{" "}
                {opsTicketPreview.department || "—"}
              </div>
            </div>
          </div>
        ) : null}
        <div className="split-layout">
          <div className="card panel-grid">
            <h4 className="m-0">
              {tr("Resolution Note", "Afhandelnotitie")}
            </h4>
            <textarea
              className="field"
              rows={4}
              value={resolutionNote}
              onChange={(e) => setResolutionNote(e.target.value)}
              placeholder={tr(
                "What was done to resolve the issue?",
                "Wat is er gedaan om het probleem op te lossen?"
              )}
            />
            <input
              className="field"
              value={resolutionParts}
              onChange={(e) => setResolutionParts(e.target.value)}
              placeholder={tr(
                "Parts used (optional)",
                "Gebruikte onderdelen (optioneel)"
              )}
            />
            <div className="flex-gap-8">
              <input
                className="field"
                value={resolutionCost}
                onChange={(e) => setResolutionCost(e.target.value)}
                placeholder={tr("Cost (optional)", "Kosten (optioneel)")}
              />
              <input
                className="field"
                value={resolutionMinutes}
                onChange={(e) => setResolutionMinutes(e.target.value)}
                placeholder={tr(
                  "Time spent min (optional)",
                  "Bestede tijd min (optioneel)"
                )}
              />
            </div>
            <button
              onClick={submitResolutionNote}
              disabled={busy || !hasSession}
            >
              {tr("Save resolution note", "Afhandelnotitie opslaan")}
            </button>
          </div>
          <div className="card panel-grid">
            <h4 className="m-0">
              {tr("Classification Override", "Classificatie-override")}
            </h4>
            <div className="flex-gap-8">
              <select
                className="field"
                value={overrideField}
                onChange={(e) =>
                  setOverrideField(
                    e.target.value as "category" | "priority" | "department"
                  )
                }
              >
                <option value="category">
                  {tr("category", "categorie")}
                </option>
                <option value="priority">
                  {tr("priority", "prioriteit")}
                </option>
                <option value="department">
                  {tr("department", "afdeling")}
                </option>
              </select>
              <input
                className="field"
                value={overrideValue}
                onChange={(e) => setOverrideValue(e.target.value)}
                placeholder={tr(
                  "New manager value",
                  "Nieuwe beheerderswaarde"
                )}
              />
            </div>
            <button
              onClick={submitClassificationOverride}
              disabled={busy || !hasSession}
            >
              {tr("Save override", "Override opslaan")}
            </button>
          </div>
        </div>
        <div className="split-layout">
          <div className="card panel-grid">
            <h4 className="m-0">
              {tr(
                "Resolution Notes History",
                "Geschiedenis afhandelnotities"
              )}
            </h4>
            <div className="admin-scroll-220">
              {opsNotes.length === 0 ? (
                <p className="text-muted m-0">
                  {t("adminSettings.noNotesLoaded")}
                </p>
              ) : (
                opsNotes.map((n) => (
                  <div key={n.id} className="admin-list-row">
                    <div className="admin-meta-label">
                      #{n.id} {tr("by", "door")} {n.added_by || "admin"}{" "}
                      {tr("at", "om")}{" "}
                      {new Date(n.created_at).toLocaleString()}
                    </div>
                    <div>{n.note}</div>
                    {(n.parts_used ||
                      n.time_spent_minutes ||
                      n.cost !== null) && (
                      <div className="admin-meta-label">
                        {n.parts_used
                          ? `${tr("parts", "onderdelen")}: ${n.parts_used}`
                          : ""}
                        {n.time_spent_minutes
                          ? ` | ${tr("minutes", "minuten")}: ${n.time_spent_minutes}`
                          : ""}
                        {n.cost !== null
                          ? ` | ${tr("cost", "kosten")}: ${n.cost}`
                          : ""}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
          <div className="card panel-grid">
            <h4 className="m-0">
              {tr(
                "Classification Override History",
                "Geschiedenis classificatie-overrides"
              )}
            </h4>
            <div className="admin-scroll-220">
              {opsOverrides.length === 0 ? (
                <p className="text-muted m-0">
                  {t("adminSettings.noOverridesLoaded")}
                </p>
              ) : (
                opsOverrides.map((o) => (
                  <div key={o.id} className="admin-list-row">
                    <div className="admin-meta-label">
                      #{o.id} {tr("by", "door")} {o.changed_by || "admin"}{" "}
                      {tr("at", "om")}{" "}
                      {new Date(o.created_at).toLocaleString()}
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
      </div>
      <p className="u-mt-12">{status}</p>
    </>
  );
}
