"use client";

import { useI18n } from "../i18n/I18nProvider";
import { TicketBadge } from "./TicketBadge";

const STATUS_FLOW = ["Open", "In Progress", "Resolved"] as const;
type SortKey = "id" | "created_at" | "priority" | "status";
type SortDir = "asc" | "desc";

export function TicketTable({
  tickets,
  onStatusChange,
  sortKey,
  sortDir,
  onSortChange,
  onSelectTicket,
  showCreatedBy = true,
}: {
  tickets: any[];
  onStatusChange: (ticketId: number, status: string) => void;
  sortKey: SortKey;
  sortDir: SortDir;
  onSortChange: (key: SortKey) => void;
  onSelectTicket?: (ticket: any) => void;
  showCreatedBy?: boolean;
}) {
  const { t } = useI18n();

  function statusLabel(value: string) {
    if (value === "Open") return t("dashboard.statusOpen");
    if (value === "In Progress") return t("dashboard.statusInProgress");
    if (value === "Resolved") return t("dashboard.statusResolved");
    return value;
  }

  function sortIndicator(key: SortKey) {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? " ↑" : " ↓";
  }

  return (
    <div className="card">
      <table style={{ width: "100%", borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th align="left">
              <button
                className="btn btn-ghost"
                style={{ padding: "4px 8px" }}
                onClick={() => onSortChange("id")}
              >
                {t("dashboard.colId")}
                {sortIndicator("id")}
              </button>
            </th>
            <th align="left">{t("dashboard.colMessage")}</th>
            <th align="left">{t("dashboard.colIssueSummary")}</th>
            {showCreatedBy ? (
              <th align="left">{t("dashboard.colCreatedBy")}</th>
            ) : null}
            <th align="left">{t("dashboard.colCategory")}</th>
            <th align="left">
              <button
                className="btn btn-ghost"
                style={{ padding: "4px 8px" }}
                onClick={() => onSortChange("priority")}
              >
                {t("dashboard.colPriority")}
                {sortIndicator("priority")}
              </button>
            </th>
            <th align="left">
              <button
                className="btn btn-ghost"
                style={{ padding: "4px 8px" }}
                onClick={() => onSortChange("status")}
              >
                {t("dashboard.colStatus")}
                {sortIndicator("status")}
              </button>
            </th>
            <th align="left">
              <button
                className="btn btn-ghost"
                style={{ padding: "4px 8px" }}
                onClick={() => onSortChange("created_at")}
              >
                {t("dashboard.colCreated")}
                {sortIndicator("created_at")}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((row) => (
            <tr
              key={row.id}
              onClick={() => onSelectTicket?.(row)}
              style={{ cursor: onSelectTicket ? "pointer" : "default" }}
            >
              <td>{row.id}</td>
              <td className="text-muted">"{row.message}"</td>
              <td>{row.issue_summary || "-"}</td>
              {showCreatedBy ? (
                <td>
                  {row.created_by_username ??
                    (row.created_by_user_id != null
                      ? t("dashboard.userNum", { id: row.created_by_user_id })
                      : t("common.emDash"))}
                </td>
              ) : null}
              <td>{row.category}</td>
              <td>
                <TicketBadge label={row.priority} />
              </td>
              <td>
                <select
                  value={row.status}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => onStatusChange(row.id, e.target.value)}
                >
                  {STATUS_FLOW.map((s) => (
                    <option key={s} value={s}>
                      {statusLabel(s)}
                    </option>
                  ))}
                </select>
              </td>
              <td>{new Date(row.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
