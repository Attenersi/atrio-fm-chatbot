"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getSession,
  getStats,
  getTickets,
  updateTicketStatus,
} from "../../../lib/api";
import { TicketTable } from "../../../components/TicketTable";
import { useRouter } from "next/navigation";
import { useI18n } from "../../../i18n/I18nProvider";

const CATEGORY_OPTIONS = [
  "",
  "HVAC",
  "Electrical",
  "Plumbing",
  "Safety",
  "General",
];
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
  const { t } = useI18n();
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  if (!entries.length) {
    return <p className="text-muted m-0">{t("dashboard.chartNoData")}</p>;
  }
  return (
    <div className="dash-chart-grid">
      {entries.map(([label, value]) => (
        <div key={label}>
          <div className="dash-bar-meta">
            <span>{label}</span>
            <span style={{ fontWeight: 600 }}>{value}</span>
          </div>
          <div className="dash-bar-track">
            <div
              className="dash-bar-fill"
              style={{ width: `${Math.round((value / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function TrendBarChart({ data }: { data: Record<string, number> }) {
  const { t } = useI18n();
  const keys = Object.keys(data).sort();
  const max = Math.max(1, ...keys.map((k) => data[k] ?? 0));
  if (!keys.length) {
    return (
      <p className="text-muted m-0">{t("dashboard.chartNoTickets30d")}</p>
    );
  }
  return (
    <div className="dash-trend-wrap">
      {keys.map((day) => {
        const v = data[day] ?? 0;
        const h = Math.max(8, Math.round((v / max) * 100));
        return (
          <div key={day} className="dash-trend-col">
            <div
              className="dash-trend-bar"
              style={{ height: h }}
              title={`${day}: ${v}`}
            />
            <span className="dash-trend-label">{day.slice(5)}</span>
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const { t } = useI18n();
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
    const escapeCsv = (v: unknown) =>
      `"${String(v ?? "").replaceAll('"', '""')}"`;
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
      return (
        ((PRIORITY_WEIGHT[a.priority] ?? 0) -
          (PRIORITY_WEIGHT[b.priority] ?? 0)) *
        direction
      );
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

  function statusFilterLabel(v: string) {
    if (!v) return t("dashboard.filterAllStatuses");
    if (v === "Open") return t("dashboard.statusOpen");
    if (v === "In Progress") return t("dashboard.statusInProgress");
    if (v === "Resolved") return t("dashboard.statusResolved");
    return v;
  }

  if (!ready) {
    return (
      <section className="page-shell">
        <p>{t("common.checkingSession")}</p>
      </section>
    );
  }

  return (
    <div className="page-shell">
      <h1>
        {role === "admin"
          ? t("dashboard.titleAdmin")
          : t("dashboard.titleUser")}
      </h1>
      <div className="stats-grid">
        <div className="card">
          {t("dashboard.total")}: {stats.total ?? 0}
        </div>
        <div className="card">
          {t("dashboard.urgent")}: {stats.urgent ?? 0}
        </div>
      </div>
      {Object.keys(stats.by_category ?? {}).length > 0 ||
      Object.keys(stats.by_day ?? {}).length > 0 ? (
        <div className="dashboard-charts-grid">
          <div className="card panel-grid">
            <h3 className="card-title-flush">
              {t("dashboard.chartByCategory")}
            </h3>
            <CategoryBarChart data={stats.by_category ?? {}} />
          </div>
          <div className="card panel-grid">
            <h3 className="card-title-flush">{t("dashboard.chartNew30d")}</h3>
            <TrendBarChart data={stats.by_day ?? {}} />
          </div>
        </div>
      ) : null}
      <div className="card toolbar">
        <select
          className="field field-w-180"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          {CATEGORY_OPTIONS.map((v) => (
            <option key={v || "all"} value={v}>
              {v || t("dashboard.filterAllCategories")}
            </option>
          ))}
        </select>
        <select
          className="field field-w-160"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          {PRIORITY_OPTIONS.map((v) => (
            <option key={v || "all"} value={v}>
              {v || t("dashboard.filterAllPriorities")}
            </option>
          ))}
        </select>
        <select
          className="field field-w-170"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {STATUS_OPTIONS.map((v) => (
            <option key={v || "all"} value={v}>
              {statusFilterLabel(v)}
            </option>
          ))}
        </select>
        <button
          onClick={exportCsv}
          type="button"
          className="btn btn-ghost btn-sm"
        >
          {t("dashboard.exportCsv")}
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
      <div className="card toolbar toolbar-spread">
        <span>
          {t("dashboard.showing", {
            from: sortedTickets.length === 0 ? 0 : pageStart + 1,
            to: Math.min(pageStart + PAGE_SIZE, sortedTickets.length),
            total: sortedTickets.length,
          })}
        </span>
        <div className="flex-gap-8">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={currentPage <= 1}
          >
            {t("dashboard.prev")}
          </button>
          <span className="align-self-center">
            {t("dashboard.pageOf", { current: currentPage, total: totalPages })}
          </span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={currentPage >= totalPages}
          >
            {t("dashboard.next")}
          </button>
        </div>
      </div>

      {selectedTicket ? (
        <div
          className="drawer-overlay"
          onClick={() => setSelectedTicket(null)}
        >
          <aside
            className="card drawer-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="drawer-header-row">
              <h3 className="m-0">
                {t("dashboard.detailTicket", { id: selectedTicket.id })}
              </h3>
              <div className="flex-gap-8">
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() =>
                    hasPrevTicket &&
                    setSelectedTicket(sortedTickets[selectedTicketIndex - 1])
                  }
                  disabled={!hasPrevTicket}
                >
                  {t("dashboard.prev")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() =>
                    hasNextTicket &&
                    setSelectedTicket(sortedTickets[selectedTicketIndex + 1])
                  }
                  disabled={!hasNextTicket}
                >
                  {t("dashboard.next")}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  onClick={() => setSelectedTicket(null)}
                >
                  {t("dashboard.close")}
                </button>
              </div>
            </div>
            <div className="card drawer-detail-block">
              <p style={{ margin: "0 0 8px" }}>
                <strong>{t("dashboard.issueSummary")}</strong>
              </p>
              <p className="m-0">{selectedTicket.issue_summary || "-"}</p>
            </div>
            <div className="card drawer-detail-block">
              <p style={{ margin: "0 0 8px" }}>
                <strong>{t("dashboard.messageQuote")}</strong>
              </p>
              <p className="m-0 text-muted">
                "{selectedTicket.message}"
              </p>
            </div>
            {role === "admin" ? (
              <div className="card drawer-detail-block">
                <p style={{ margin: "0 0 8px" }}>
                  <strong>{t("dashboard.createdBy")}</strong>
                </p>
                <p className="m-0">
                  {selectedTicket.created_by_username ??
                    (selectedTicket.created_by_user_id != null
                      ? t("dashboard.userNum", {
                          id: selectedTicket.created_by_user_id,
                        })
                      : t("common.emDash"))}
                </p>
              </div>
            ) : null}
            <div className="grid-2">
              <div className="card drawer-detail-block">
                <p className="m-0">
                  <strong>{t("dashboard.categoryLabel")}:</strong>{" "}
                  {selectedTicket.category}
                </p>
              </div>
              <div className="card drawer-detail-block">
                <p className="m-0">
                  <strong>{t("dashboard.priorityLabel")}:</strong>{" "}
                  {selectedTicket.priority}
                </p>
              </div>
              <div className="card drawer-detail-block">
                <p className="m-0">
                  <strong>{t("dashboard.statusLabel")}:</strong>{" "}
                  {statusFilterLabel(selectedTicket.status)}
                </p>
              </div>
              <div className="card drawer-detail-block">
                <p className="m-0">
                  <strong>{t("dashboard.departmentLabel")}:</strong>{" "}
                  {selectedTicket.department}
                </p>
              </div>
            </div>
            <div className="card drawer-detail-block">
              <p style={{ margin: "0 0 8px" }}>
                <strong>{t("dashboard.assistantResponse")}</strong>
              </p>
              <p className="m-0">{selectedTicket.response || "-"}</p>
            </div>
            <p className="m-0 text-muted" style={{ fontSize: 13 }}>
              {t("dashboard.createdLabel")}:{" "}
              {new Date(selectedTicket.created_at).toLocaleString()}
            </p>
          </aside>
        </div>
      ) : null}
    </div>
  );
}
