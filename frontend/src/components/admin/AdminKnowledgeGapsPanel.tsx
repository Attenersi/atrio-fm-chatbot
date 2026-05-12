"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useI18n } from "../../i18n/I18nProvider";
import { adminListKnowledgeGaps, getSession, type KnowledgeGap } from "../../lib/api";
import { formatGapReason } from "../../lib/adminShared";

export function AdminKnowledgeGapsPanel() {
  const { locale, t } = useI18n();
  const tr = (en: string, nl: string) => (locale === "nl" ? nl : en);
  const router = useRouter();
  const [adminUsername, setAdminUsername] = useState("");
  const [busy, setBusy] = useState(false);
  const [gaps, setGaps] = useState<KnowledgeGap[]>([]);
  const [gapFilter, setGapFilter] = useState<
    "" | "new" | "reviewed" | "resolved"
  >("");
  const [status, setStatus] = useState(
    tr("Sign in to load gaps.", "Log in om lacunes te laden.")
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

  useEffect(() => {
    if (!hasSession) return;
    void loadGaps({ quiet: true });
  }, [hasSession, gapFilter]);

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

  return (
    <>
      <div className="card panel-grid">
        <h3>{t("adminSettings.tabsKnowledge")}</h3>
        <div className="toolbar">
          <select
            className="field"
            style={{ width: 180 }}
            value={gapFilter}
            onChange={(e) =>
              setGapFilter(
                e.target.value as "" | "new" | "reviewed" | "resolved"
              )
            }
          >
            <option value="">{t("adminSettings.allStatuses")}</option>
            <option value="new">new</option>
            <option value="reviewed">reviewed</option>
            <option value="resolved">resolved</option>
          </select>
          <button onClick={() => loadGaps()} disabled={busy || !hasSession}>
            {t("adminSettings.refresh")} {tr("gaps", "lacunes")}
          </button>
        </div>
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th align="left">ID</th>
                <th align="left">{tr("Question", "Vraag")}</th>
                <th align="left">{tr("Ticket", "Ticket")}</th>
                <th align="left">{tr("Category", "Categorie")}</th>
                <th align="left">{tr("Status", "Status")}</th>
                <th align="left">{tr("Reason", "Reden")}</th>
                <th align="left">{tr("Created", "Aangemaakt")}</th>
                <th align="left">{tr("Action", "Actie")}</th>
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
                          <span className="knowledge-gap-reason-title">
                            {r.title}
                          </span>
                          {r.detail ? (
                            <span className="knowledge-gap-reason-detail">
                              {r.detail}
                            </span>
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
                      {tr("Resolve...", "Oplossen...")}
                    </button>
                  </td>
                </tr>
              ))}
              {gaps.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-muted">
                    {t("adminSettings.noKnowledgeGaps")}
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
      <p style={{ marginTop: 12 }}>{status}</p>
    </>
  );
}
