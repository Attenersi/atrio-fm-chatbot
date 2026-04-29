import { TicketBadge } from "./TicketBadge";

const STATUS_FLOW = ["Open", "In Progress", "Resolved"];
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
              <button className="btn btn-ghost" style={{ padding: "4px 8px" }} onClick={() => onSortChange("id")}>ID{sortIndicator("id")}</button>
            </th>
            <th align="left">Message</th>
            <th align="left">Issue Summary</th>
            {showCreatedBy ? <th align="left">Created by</th> : null}
            <th align="left">Category</th>
            <th align="left">
              <button className="btn btn-ghost" style={{ padding: "4px 8px" }} onClick={() => onSortChange("priority")}>
                Priority{sortIndicator("priority")}
              </button>
            </th>
            <th align="left">
              <button className="btn btn-ghost" style={{ padding: "4px 8px" }} onClick={() => onSortChange("status")}>
                Status{sortIndicator("status")}
              </button>
            </th>
            <th align="left">
              <button className="btn btn-ghost" style={{ padding: "4px 8px" }} onClick={() => onSortChange("created_at")}>
                Created{sortIndicator("created_at")}
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr
              key={t.id}
              onClick={() => onSelectTicket?.(t)}
              style={{ cursor: onSelectTicket ? "pointer" : "default" }}
            >
              <td>{t.id}</td>
              <td className="text-muted">"{t.message}"</td>
              <td>{t.issue_summary || "-"}</td>
              {showCreatedBy ? (
                <td>{t.created_by_username ?? (t.created_by_user_id != null ? `#${t.created_by_user_id}` : "—")}</td>
              ) : null}
              <td>{t.category}</td>
              <td>
                <TicketBadge label={t.priority} />
              </td>
              <td>
                <select
                  value={t.status}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => onStatusChange(t.id, e.target.value)}
                >
                  {STATUS_FLOW.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </td>
              <td>{new Date(t.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
