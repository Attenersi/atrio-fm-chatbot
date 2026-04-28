"use client";

import { useEffect, useMemo, useState } from "react";
import { getSession, getStats, getTickets, updateTicketStatus } from "../../../lib/api";
import { TicketTable } from "../../../components/TicketTable";
import { useRouter } from "next/navigation";

const CATEGORY_OPTIONS = ["", "HVAC", "Electrical", "Plumbing", "Safety", "General"];
const PRIORITY_OPTIONS = ["", "URGENT", "HIGH", "NORMAL", "LOW"];
const STATUS_OPTIONS = ["", "Open", "In Progress", "Resolved"];
const PAGE_SIZE = 8;
type SortKey = "id" | "created_at" | "priority" | "status";
type SortDir = "asc" | "desc";
const PRIORITY_WEIGHT: Record<string, number> = {
  URGENT: 4,
  HIGH: 3,
  NORMAL: 2,
  LOW: 1,
};

function CategoryBarChart({ data }: { data: Record<string, number> }) {
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) {
    return <p style={{ margin: 0, color: "var(--muted)" }}>No data.</p>;
  }
  return (
    <div style={{ display: "grid", gap: 10 }}>
      {entries.map(([label, value]) => (
        <div key={label}>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 13,
              marginBottom: 4,
            }}
          >
            <span>{label}</span>
            <span style={{ fontWeight: 600 }}>{value}</span>
          </div>
          <div
            style={{
              height: 10,
              borderRadius: 5,
              background: "var(--border)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${Math.round((value / max) * 100)}%`,
                height: "100%",
                background: "var(--color-action-accent)",
                borderRadius: 5,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function TrendBarChart({ data }: { data: Record<string, number> }) {
  const keys = Object.keys(data).sort();
  const max = Math.max(1, ...keys.map((k) => data[k] ?? 0));
  if (!keys.length) {
    return <p style={{ margin: 0, color: "var(--muted)" }}>No tickets in the last 30 days.</p>;
  }
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-end",
        gap: 6,
        minHeight: 120,
        flexWrap: "wrap",
        paddingTop: 8,
      }}
    >
      {keys.map((day) => {
        const v = data[day] ?? 0;
        const h = Math.max(8, Math.round((v / max) * 100));
        return (
          <div
            key={day}
            style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}
          >
            <div
              style={{
                width: 12,
                height: h,
                borderRadius: 4,
                background: "var(--color-brand-primary)",
              }}
              title={`${day}: ${v}`}
            />
            <span style={{ fontSize: 10, color: "var(--muted)" }}>{day.slice(5)}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [role, setRole] = useState<"admin" | "user">("user");
  const [tickets, setTickets] = useState<any[]>([]);
  const [stats, setStats] = useState<any>({});
  const [category, setCategory] = useState("");
  const [priority, setPriority] = useState("");
  const [status, setStatus] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("id");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(1);
  const [selectedTicket, setSelectedTicket] = useState<any | null>(null);

  async function refresh() {
    const [ticketResp, statsResp] = await Promise.all([
      getTickets({
        category: category || undefined,
        priority: priority || undefined,
        status: status || undefined,
      }),
      getStats(),
    ]);
    setTickets(ticketResp.tickets ?? []);
    setStats(statsResp ?? {});
  }

  useEffect(() => {
    getSession()
      .then((res) => {
        setRole(res.user.role);
        setReady(true);
      })
      .catch(() => router.replace("/"));
  }, [router]);

  useEffect(() => {
    if (!ready) return;
    refresh();
  }, [category, priority, status, ready]);

  useEffect(() => {
    setPage(1);
  }, [category, priority, status, sortKey, sortDir, tickets.length]);

  async function onStatusChange(ticketId: number, status: string) {
    await updateTicketStatus(ticketId, status);
    await refresh();
  }

  function exportCsv() {
    const headers = [
      "id",
      "message",
      "issue_summary",
      "category",
      "priority",
      "department",
      "response",
      "status",
      "created_at",
      "created_by_username",
      "created_by_user_id",
    ];
    const escapeCsv = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
    const rows = tickets.map((t) =>
      [
        t.id,
        t.message,
        t.issue_summary,
        t.category,
        t.priority,
        t.department,
        t.response,
        t.status,
        t.created_at,
        t.created_by_username ?? "",
        t.created_by_user_id ?? "",
      ]
        .map(escapeCsv)
        .join(",")
    );
    const csv = [headers.join(","), ...rows].join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "tickets.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  function onSortChange(key: SortKey) {
    if (sortKey === key) {
      setSortDir((prev) => (prev === "asc" ? "desc" : "asc"));
      return;
    }
    setSortKey(key);
    setSortDir("desc");
  }

  const sortedTickets = [...tickets].sort((a, b) => {
    const direction = sortDir === "asc" ? 1 : -1;
    if (sortKey === "id") return (a.id - b.id) * direction;
    if (sortKey === "created_at") {
      return (
        (new Date(a.created_at).getTime() - new Date(b.created_at).getTime()) *
        direction
      );
    }
    if (sortKey === "priority") {
      return ((PRIORITY_WEIGHT[a.priority] ?? 0) - (PRIORITY_WEIGHT[b.priority] ?? 0)) * direction;
    }
    return String(a.status).localeCompare(String(b.status)) * direction;
  });

  const totalPages = Math.max(1, Math.ceil(sortedTickets.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const pagedTickets = sortedTickets.slice(pageStart, pageStart + PAGE_SIZE);
  const selectedTicketIndex = useMemo(
    () =>
      selectedTicket
        ? sortedTickets.findIndex((t) => t.id === selectedTicket.id)
        : -1,
    [selectedTicket, sortedTickets]
  );
  const hasPrevTicket = selectedTicketIndex > 0;
  const hasNextTicket =
    selectedTicketIndex >= 0 && selectedTicketIndex < sortedTickets.length - 1;

  useEffect(() => {
    if (!selectedTicket) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setSelectedTicket(null);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [selectedTicket]);

  if (!ready) {
    return (
      <section className="page-shell">
        <p>Checking session...</p>
      </section>
    );
  }

  return (
    <div className="page-shell">
      <h1>{role === "admin" ? "Ticket Dashboard" : "My Tickets"}</h1>
      <div className="stats-grid">
        <div className="card">Total: {stats.total ?? 0}</div>
        <div className="card">Urgent: {stats.urgent ?? 0}</div>
      </div>
      {Object.keys(stats.by_category ?? {}).length > 0 || Object.keys(stats.by_day ?? {}).length > 0 ? (
        <div
          style={{
            display: "grid",
            gap: 14,
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          }}
        >
          <div className="card panel-grid">
            <h3 style={{ margin: 0 }}>Tickets by category</h3>
            <CategoryBarChart data={stats.by_category ?? {}} />
          </div>
          <div className="card panel-grid">
            <h3 style={{ margin: 0 }}>New tickets (last 30 days)</h3>
            <TrendBarChart data={stats.by_day ?? {}} />
          </div>
        </div>
      ) : null}
      <div className="card toolbar">
        <select className="field" style={{ width: 180 }} value={category} onChange={(e) => setCategory(e.target.value)}>
          {CATEGORY_OPTIONS.map((v) => (
            <option key={v || "all"} value={v}>
              {v || "All categories"}
            </option>
          ))}
        </select>
        <select className="field" style={{ width: 160 }} value={priority} onChange={(e) => setPriority(e.target.value)}>
          {PRIORITY_OPTIONS.map((v) => (
            <option key={v || "all"} value={v}>
              {v || "All priorities"}
            </option>
          ))}
        </select>
        <select className="field" style={{ width: 170 }} value={status} onChange={(e) => setStatus(e.target.value)}>
          {STATUS_OPTIONS.map((v) => (
            <option key={v || "all"} value={v}>
              {v || "All statuses"}
            </option>
          ))}
        </select>
        <button onClick={exportCsv} className="btn btn-ghost" style={{ padding: "8px 12px" }}>
          Export CSV
        </button>
      </div>
      <TicketTable
        tickets={pagedTickets}
        onStatusChange={onStatusChange}
        sortKey={sortKey}
        sortDir={sortDir}
        onSortChange={onSortChange}
        onSelectTicket={(ticket) => setSelectedTicket(ticket)}
        showCreatedBy={role === "admin"}
      />
      <div className="card toolbar" style={{ justifyContent: "space-between" }}>
        <span>
          Showing {sortedTickets.length === 0 ? 0 : pageStart + 1}-
          {Math.min(pageStart + PAGE_SIZE, sortedTickets.length)} of {sortedTickets.length}
        </span>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={currentPage <= 1}>
            Prev
          </button>
          <span style={{ alignSelf: "center" }}>
            Page {currentPage} / {totalPages}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
          >
            Next
          </button>
        </div>
      </div>

      {selectedTicket ? (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.45)",
            display: "flex",
            justifyContent: "flex-end",
            zIndex: 60,
          }}
          onClick={() => setSelectedTicket(null)}
        >
          <aside
            className="card"
            style={{
              width: "min(560px, 100%)",
              height: "100vh",
              overflowY: "auto",
              borderRadius: 0,
              display: "grid",
              gap: 12,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <h3 style={{ margin: 0 }}>Ticket #{selectedTicket.id}</h3>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() =>
                    hasPrevTicket &&
                    setSelectedTicket(sortedTickets[selectedTicketIndex - 1])
                  }
                  disabled={!hasPrevTicket}
                  style={{ background: "#fff", color: "#101828", border: "1px solid #d0d5dd" }}
                >
                  Prev
                </button>
                <button
                  type="button"
                  onClick={() =>
                    hasNextTicket &&
                    setSelectedTicket(sortedTickets[selectedTicketIndex + 1])
                  }
                  disabled={!hasNextTicket}
                  style={{ background: "#fff", color: "#101828", border: "1px solid #d0d5dd" }}
                >
                  Next
                </button>
                <button
                  type="button"
                  onClick={() => setSelectedTicket(null)}
                  style={{ background: "#fff", color: "#101828", border: "1px solid #d0d5dd" }}
                >
                  Close
                </button>
              </div>
            </div>
            <div className="card" style={{ background: "#f8fafc" }}>
              <p style={{ margin: "0 0 8px" }}><strong>Issue summary</strong></p>
              <p style={{ margin: 0 }}>{selectedTicket.issue_summary || "-"}</p>
            </div>
            <div className="card" style={{ background: "#f8fafc" }}>
              <p style={{ margin: "0 0 8px" }}><strong>Message (quote)</strong></p>
              <p style={{ margin: 0, color: "#475467" }}>"{selectedTicket.message}"</p>
            </div>
            {role === "admin" ? (
              <div className="card" style={{ background: "#f8fafc" }}>
                <p style={{ margin: "0 0 8px" }}><strong>Created by</strong></p>
                <p style={{ margin: 0 }}>
                  {selectedTicket.created_by_username ??
                    (selectedTicket.created_by_user_id != null
                      ? `User #${selectedTicket.created_by_user_id}`
                      : "—")}
                </p>
              </div>
            ) : null}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              <div className="card" style={{ background: "#f8fafc" }}>
                <p style={{ margin: 0 }}><strong>Category:</strong> {selectedTicket.category}</p>
              </div>
              <div className="card" style={{ background: "#f8fafc" }}>
                <p style={{ margin: 0 }}><strong>Priority:</strong> {selectedTicket.priority}</p>
              </div>
              <div className="card" style={{ background: "#f8fafc" }}>
                <p style={{ margin: 0 }}><strong>Status:</strong> {selectedTicket.status}</p>
              </div>
              <div className="card" style={{ background: "#f8fafc" }}>
                <p style={{ margin: 0 }}><strong>Department:</strong> {selectedTicket.department}</p>
              </div>
            </div>
            <div className="card" style={{ background: "#f8fafc" }}>
              <p style={{ margin: "0 0 8px" }}><strong>Assistant response</strong></p>
              <p style={{ margin: 0 }}>{selectedTicket.response || "-"}</p>
            </div>
            <p style={{ margin: 0, color: "#475467", fontSize: 13 }}>
              Created: {new Date(selectedTicket.created_at).toLocaleString()}
            </p>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
