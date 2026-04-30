"use client";

import type { CSSProperties, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getSession } from "../../../lib/api";

type HelpSection =
  | "overview"
  | "chat"
  | "dashboard"
  | "gaps"
  | "documents"
  | "training"
  | "quality";

const TABS: { id: HelpSection; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "chat", label: "Chat" },
  { id: "dashboard", label: "Tickets" },
  { id: "gaps", label: "Knowledge gaps" },
  { id: "documents", label: "Documents" },
  { id: "training", label: "Training review" },
  { id: "quality", label: "Training quality" },
];

const surface: CSSProperties = {
  border: "1px solid var(--border)",
  borderRadius: 10,
  background: "var(--surface)",
  padding: 14,
};

const h2: CSSProperties = {
  fontSize: "1.05rem",
  fontWeight: 600,
  margin: "24px 0 10px",
  color: "var(--color-heading, var(--text))",
};

const h3: CSSProperties = {
  fontSize: "0.95rem",
  fontWeight: 600,
  margin: "16px 0 8px",
};

const p: CSSProperties = { margin: "0 0 12px", lineHeight: 1.55, fontSize: 15 };

function Callout({
  tone,
  title,
  children,
}: {
  tone: "info" | "warn" | "danger";
  title: string;
  children: ReactNode;
}) {
  const map = {
    info: {
      bg: "var(--chip-info-bg)",
      border: "var(--chip-info-border)",
      color: "var(--chip-info-text)",
    },
    warn: {
      bg: "var(--chip-warn-bg)",
      border: "var(--chip-warn-border)",
      color: "var(--chip-warn-text)",
    },
    danger: {
      bg: "var(--chip-danger-bg)",
      border: "var(--chip-danger-border)",
      color: "var(--chip-danger-text)",
    },
  } as const;
  const t = map[tone];
  return (
    <div
      style={{
        margin: "14px 0",
        padding: "12px 14px",
        borderRadius: 10,
        border: `1px solid ${t.border}`,
        background: t.bg,
        color: t.color,
        fontSize: 14,
        lineHeight: 1.5,
      }}
    >
      <strong style={{ display: "block", marginBottom: 6 }}>{title}</strong>
      {children}
    </div>
  );
}

function Steps({ items }: { items: string[] }) {
  return (
    <ol style={{ margin: "0 0 16px", paddingLeft: 22, lineHeight: 1.55, fontSize: 14 }}>
      {items.map((s) => (
        <li key={s} style={{ marginBottom: 6 }}>
          {s}
        </li>
      ))}
    </ol>
  );
}

function DataTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div style={{ overflowX: "auto", margin: "12px 0 20px" }}>
      <table
        style={{
          width: "100%",
          borderCollapse: "collapse",
          fontSize: 13,
          border: "1px solid var(--border)",
          borderRadius: 10,
          overflow: "hidden",
        }}
      >
        <thead>
          <tr style={{ background: "var(--surface-muted)" }}>
            {headers.map((h) => (
              <th
                key={h}
                style={{
                  textAlign: "left",
                  padding: "10px 12px",
                  borderBottom: "1px solid var(--border)",
                  fontWeight: 600,
                  color: "var(--muted)",
                }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={{ background: i % 2 ? "var(--surface-muted)" : "var(--surface)" }}>
              {row.map((cell, j) => (
                <td
                  key={j}
                  style={{
                    padding: "10px 12px",
                    borderBottom: "1px solid var(--border)",
                    verticalAlign: "top",
                  }}
                >
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={surface}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          textTransform: "uppercase",
          letterSpacing: "0.04em",
          color: "var(--muted)",
          marginBottom: 8,
        }}
      >
        {title}
      </div>
      <div style={{ fontSize: 14, lineHeight: 1.5 }}>{children}</div>
    </div>
  );
}

export default function HelpPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [section, setSection] = useState<HelpSection>("overview");

  useEffect(() => {
    getSession()
      .then(() => setReady(true))
      .catch(() => router.replace("/"));
  }, [router]);

  const show = useCallback((id: HelpSection) => {
    setSection(id);
    if (typeof window !== "undefined" && window.history.replaceState) {
      window.history.replaceState(null, "", `#${id}`);
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    const hash = (window.location.hash || "").replace(/^#/, "") as HelpSection;
    const ok = TABS.some((t) => t.id === hash);
    if (ok) setSection(hash);
  }, [ready]);

  if (!ready) {
    return (
      <section className="page-shell">
        <p>Checking session...</p>
      </section>
    );
  }

  return (
    <div style={{ maxWidth: 920, margin: "0 auto", padding: "24px 20px 48px" }}>
      <h1 style={{ fontSize: "1.65rem", fontWeight: 600, margin: "0 0 8px", color: "var(--color-heading, var(--text))" }}>
        Help — Atrio FM Chatbot
      </h1>
      <p style={{ ...p, color: "var(--muted)", marginBottom: 20 }}>
        Administrator and user guide (English). For the full Polish handbook, see{" "}
        <code style={{ fontSize: 13 }}>docs/admin_guide.md</code> or <code style={{ fontSize: 13 }}>docs/admin_guide.html</code>{" "}
        in the repository.
      </p>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 20 }}>
        {TABS.map((t) => {
          const active = section === t.id;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => show(t.id)}
              aria-current={active ? "true" : undefined}
              style={{
                border: active ? "1px solid var(--color-action-accent)" : "1px solid var(--border)",
                background: active ? "color-mix(in srgb, var(--color-action-accent) 14%, transparent)" : "var(--surface)",
                color: active ? "var(--color-action-accent)" : "var(--text)",
                padding: "7px 14px",
                borderRadius: 999,
                fontSize: 13,
                fontWeight: active ? 600 : 400,
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              {t.label}
            </button>
          );
        })}
      </div>

      {section === "overview" && (
        <div>
          <p style={p}>
            Atrio FM Chatbot helps tenants and staff with building questions and service requests. Admins manage
            tickets, users, knowledge documents, and quality improvements.
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: 12,
              margin: "16px 0",
            }}
          >
            <Card title="Chat">Ask questions; the bot may create a service ticket when it detects a real issue.</Card>
            <Card title="Admin">Tickets, knowledge gaps, users, documents, training data, and quality tools.</Card>
            <Card title="Quality">Group errors, run evaluations, apply safe prompt tweaks without code.</Card>
          </div>
          <h2 style={h2}>Where things live</h2>
          <DataTable
            headers={["Route / tab", "Purpose", "Who"]}
            rows={[
              ["/chat", "Talk to the FM assistant", "Signed-in users"],
              ["/dashboard", "Ticket list and filters", "Signed-in users"],
              ["/admin → Tickets", "Resolution notes, classification overrides", "Admin"],
              ["/admin → Knowledge gaps", "Questions the bot could not answer from docs", "Admin"],
              ["/admin → Users", "Accounts and roles", "Admin"],
              ["/admin → Documents", "Knowledge base files and reindex", "Admin"],
              ["/admin/training", "Review training examples", "Admin"],
              ["/admin/training-quality", "Eval runs, analyzer, prompt overrides", "Admin"],
            ]}
          />
          <Callout tone="info" title="First-time admin sign-in">
            Open <code>/admin/login</code> (or use the main sign-in if your account is admin). Default username is often{" "}
            <code>admin</code>; password is set by your technical contact.
          </Callout>
          <Callout tone="warn" title="Daily habit">
            Check <strong>Knowledge gaps</strong> regularly. Each gap is a missing answer in your documentation.
          </Callout>
        </div>
      )}

      {section === "chat" && (
        <div>
          <p style={{ ...p, color: "var(--muted)" }}>
            <strong>Route:</strong> <code>/chat</code>
          </p>
          <h2 style={h2}>How to chat</h2>
          <Steps
            items={[
              "Open Chat from the sidebar.",
              "Type your question or issue at the bottom.",
              "Press Enter or Send.",
              "Read the reply, category, priority, and whether a ticket was created.",
            ]}
          />
          <h2 style={h2}>When the bot usually creates a ticket</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 }}>
            <Card title="Creates a ticket">
              Physical fault, safety risk, HVAC / electrical / plumbing / elevators, clear repair need.
            </Card>
            <Card title="Often no ticket">
              Hours, policies, “where is…”, thank-yous, status of an existing ticket (informational only).
            </Card>
          </div>
          <h2 style={h2}>Priorities (short)</h2>
          <DataTable
            headers={["Priority", "Use when", "Example"]}
            rows={[
              ["URGENT", "Immediate danger to people or property", "Fire, gas smell, flooding electrical hazard"],
              ["HIGH", "Serious fault, same-day action", "No heat in winter, server room cooling down"],
              ["NORMAL", "Annoying but not critical", "Stuck door, broken light in corridor"],
              ["LOW", "Minor convenience", "Cosmetic fix, furniture swap"],
            ]}
          />
          <h3 style={h3}>“Create ticket anyway”</h3>
          <p style={p}>
            If the bot answered but you still need a ticket, use the button under the message (manual ticket).
          </p>
          <h3 style={h3}>New chat</h3>
          <p style={p}>
            Use <strong>New chat</strong> when you change topic. The bot remembers recent messages in the active thread.
          </p>
          <Callout tone="info" title="Rate limit">
            Roughly 30 chat messages per minute per user. If you see “too many requests”, wait a minute.
          </Callout>
          <Callout tone="danger" title="Do not">
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              <li>Rely on chat alone for life-safety emergencies — call your emergency line.</li>
              <li>Spam the same question; it confuses context.</li>
              <li>Assume a ticket exists without checking the dashboard.</li>
            </ul>
          </Callout>
        </div>
      )}

      {section === "dashboard" && (
        <div>
          <p style={{ ...p, color: "var(--muted)" }}>
            <strong>Route:</strong> <code>/dashboard</code>
          </p>
          <p style={p}>
            Admins see all tickets; regular users see only their own. Use filters for category, priority, and status.
          </p>
          <h2 style={h2}>Change ticket status</h2>
          <Steps
            items={[
              "Open a ticket row or detail.",
              "Pick status: Open → In Progress → Resolved when work is confirmed.",
            ]}
          />
          <DataTable
            headers={["Status", "Meaning"]}
            rows={[
              ["Open", "New, not yet picked up"],
              ["In Progress", "Someone is working on it"],
              ["Resolved", "Fixed or closed with confirmation"],
            ]}
          />
          <h2 style={h2}>Admin: resolution notes</h2>
          <p style={p}>
            Under <code>/admin</code> → Tickets, add <strong>resolution notes</strong>: what was done, parts, cost, time
            spent.
          </p>
          <h2 style={h2}>Admin: classification override</h2>
          <p style={p}>
            If the bot misclassified a ticket, use <strong>Classification override</strong> to fix category, priority,
            or department. This is logged and feeds training data.
          </p>
          <p style={p}>
            <strong>Export CSV</strong> exports what you currently see after filters.
          </p>
          <Callout tone="warn" title="Do not">
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              <li>Mark Resolved without confirmation from the technician.</li>
              <li>Ignore URGENT tickets in the queue.</li>
            </ul>
          </Callout>
        </div>
      )}

      {section === "gaps" && (
        <div>
          <p style={{ ...p, color: "var(--muted)" }}>
            <strong>Route:</strong> <code>/admin</code> → <strong>Knowledge gaps</strong>
          </p>
          <p style={p}>
            Gaps are real user questions where the bot could not ground an answer in your FM documents. Closing a gap
            improves answers for everyone.
          </p>
          <h2 style={h2}>Close a gap (typical flow)</h2>
          <Steps
            items={[
              "Open the gap (or its detail page).",
              "Set Doc name, e.g. building_hours.md.",
              "Write Content in English (the assistant runs in English).",
              "Choose append (add to file) or overwrite (replace entire file).",
              "Enable Auto-reindex so the bot picks up the text immediately.",
              "Click Resolve gap.",
            ]}
          />
          <Callout tone="info" title="Tip">
            Prefer <strong>append</strong> to existing topic files unless you are sure overwrite is safe.
          </Callout>
          <Callout tone="danger" title="Do not">
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              <li>Skip Auto-reindex and expect instant better answers.</li>
              <li>Overwrite a large file without reading what is already there.</li>
            </ul>
          </Callout>
        </div>
      )}

      {section === "documents" && (
        <div>
          <p style={{ ...p, color: "var(--muted)" }}>
            <strong>Route:</strong> <code>/admin</code> → <strong>Documents</strong>
          </p>
          <p style={p}>
            Markdown / text files in the FM corpus power retrieval. After any edit, run <strong>Reindex</strong> so
            embeddings match the files.
          </p>
          <h2 style={h2}>Common doc files</h2>
          <DataTable
            headers={["File", "Topic"]}
            rows={[
              ["01_building_general_info.md", "General building info"],
              ["02_hvac_systems.md", "HVAC"],
              ["03_electrical_systems.md", "Electrical"],
              ["04_plumbing_water.md", "Plumbing / water"],
              ["05_fire_safety_emergency.md", "Fire & emergency"],
              ["06_security_access.md", "Security & access"],
              ["07_parking_transport.md", "Parking & transport"],
              ["08_it_network.md", "IT & network"],
              ["09_elevators.md", "Elevators"],
              ["10_cleaning_waste.md", "Cleaning & waste"],
              ["11_meeting_rooms_spaces.md", "Meeting rooms"],
              ["12_building_rules_policies.md", "Policies"],
            ]}
          />
          <h2 style={h2}>Upload</h2>
          <p style={p}>
            Supported: <code>.txt</code>, <code>.md</code>, <code>.csv</code>, <code>.pdf</code>, <code>.docx</code>.
            Use Overwrite and Auto-reindex as needed.
          </p>
          <Callout tone="warn" title="Most common mistake">
            Editing a document and forgetting <strong>Reindex</strong> — users still get old answers until you reindex.
          </Callout>
        </div>
      )}

      {section === "training" && (
        <div>
          <p style={{ ...p, color: "var(--muted)" }}>
            <strong>Route:</strong> <code>/admin/training</code>
          </p>
          <p style={p}>
            Review examples produced from chat/tests. Approving good rows and fixing bad ones builds a high-quality
            dataset for future model work.
          </p>
          <DataTable
            headers={["Filter", "Meaning"]}
            rows={[
              ["pending", "Needs human review"],
              ["approved", "Accepted as correct"],
              ["edited", "You corrected ideal output"],
              ["rejected", "Not suitable for training"],
            ]}
          />
          <p style={p}>
            Keyboard: <code>←</code> <code>→</code> navigate, <code>A</code> approve, <code>R</code> reject.
          </p>
          <Callout tone="warn" title="Do not">
            Approve rows without checking category and priority. Bulk-reject pending without reading.
          </Callout>
        </div>
      )}

      {section === "quality" && (
        <div>
          <p style={{ ...p, color: "var(--muted)" }}>
            <strong>Route:</strong> <code>/admin/training-quality</code>
          </p>
          <p style={p}>
            <strong>Mismatch groups</strong> show error patterns. <strong>Run eval</strong> runs a batch test (~80
            cases). <strong>Analyze pending</strong> asks the analyzer model for suggested prompt additions (cached,
            rate-limited). <strong>Active overrides</strong> are live extra rules appended to the assistant instructions.
          </p>
          <h2 style={h2}>Suggested workflow</h2>
          <Steps
            items={[
              "Run eval to capture a baseline score.",
              "Review mismatch groups so you know what is failing.",
              "Run Analyze pending; read each suggestion carefully.",
              "Apply only changes you understand; edit text in the modal if needed.",
              "Run eval again later and compare accuracy; rollback if metrics worsen.",
            ]}
          />
          <DataTable
            headers={["Constraint", "What to do"]}
            rows={[
              ["Only one eval at a time", "Wait for running to finish before starting another"],
              ["Limited active overrides", "Rollback old rules before adding new ones if you hit the cap"],
              ["Fresh eval may be required before apply", "Run eval if the UI says baseline is too old"],
            ]}
          />
          <Callout tone="danger" title="Do not">
            <ul style={{ margin: 0, paddingLeft: 18 }}>
              <li>Apply overrides you do not understand.</li>
              <li>Ignore accuracy deltas after a change.</li>
              <li>Run heavy eval repeatedly during peak chat hours if your API quota is tight.</li>
            </ul>
          </Callout>
        </div>
      )}

      <footer style={{ marginTop: 36, paddingTop: 16, borderTop: "1px solid var(--border)", fontSize: 13, color: "var(--muted)" }}>
        In-app Help (English) · Repository: <code>docs/admin_guide.md</code>, <code>docs/admin_guide.html</code>
      </footer>
    </div>
  );
}
