import { useState } from "react";

const categories = [
  {
    id: "channels",
    icon: "CH",
    name: "Communication channels",
    desc: "Where tenants can reach Atrio",
    features: [
      { name: "Web chat widget", desc: "Embeddable JS snippet on any website or intranet. Tenant opens chat overlay, describes problem, gets instant response.", phase: "mvp", competitor: "FacilityBot, FaultFixers" },
      { name: "WhatsApp integration", desc: "Tenants text a WhatsApp number. Atrio reads the message, creates ticket, responds. Most natural channel — no app install needed.", phase: "v2", competitor: "FacilityBot (core feature)" },
      { name: "Microsoft Teams bot", desc: "For corporate buildings where tenants already live in Teams. Report issues without leaving the app.", phase: "v2", competitor: "FacilityBot, ServiceChannel" },
      { name: "Slack bot", desc: "Same as Teams but for tech companies and startups.", phase: "v2", competitor: "FacilityBot" },
      { name: "Email ingestion", desc: "Tenants email support@building.com → Atrio parses the email, creates ticket, responds automatically.", phase: "v2", competitor: "Most CMMS systems" },
      { name: "QR codes in building", desc: "QR poster in lobby, elevator, bathroom → scan → opens chat. Each QR encodes location (floor, room) so ticket is pre-tagged.", phase: "mvp", competitor: "FacilityBot, FixHub" },
      { name: "SMS/text fallback", desc: "For buildings with older tenant demographics. Text a number, get support.", phase: "v3", competitor: "FacilityBot" },
      { name: "Tenant portal (web)", desc: "Full web portal where tenants log in, see their tickets, track status, submit new issues. Custom subdomain per client.", phase: "v2", competitor: "FacilityBot, Facilio" },
    ]
  },
  {
    id: "ai",
    icon: "AI",
    name: "AI intelligence",
    desc: "What makes Atrio smarter than a form",
    features: [
      { name: "Natural language understanding", desc: "Tenant describes problem in plain language ('the AC is broken in 204'). AI extracts: what, where, how urgent.", phase: "mvp", competitor: "FacilityBot, emerging" },
      { name: "Auto-classification", desc: "Every message auto-categorized: HVAC, Electrical, Plumbing, Safety, General. Custom categories per client.", phase: "mvp", competitor: "FacilityBot (partial)" },
      { name: "Priority scoring", desc: "AI assigns Urgent/High/Normal/Low based on issue description, keywords, and context. 'Water on electrical' → Urgent.", phase: "mvp", competitor: "Rare — most rely on manual" },
      { name: "Knowledge base RAG", desc: "Answers from building docs before creating a ticket. 'What's the WiFi password?' → instant answer, no ticket needed.", phase: "mvp", competitor: "FacilityBot (FAQ only)" },
      { name: "Smart routing", desc: "Auto-assign to correct department/technician based on category, location, availability, and skills.", phase: "v2", competitor: "ServiceChannel, Facilio" },
      { name: "Duplicate detection", desc: "If 5 tenants report 'no hot water floor 3' within an hour, merge into one ticket instead of creating 5.", phase: "v2", competitor: "FexaAI" },
      { name: "Sentiment analysis", desc: "Detect frustrated/angry tenants → auto-escalate priority. 'I've reported this 3 times!' → flag for manager.", phase: "v2", competitor: "Emerging feature" },
      { name: "Predictive patterns", desc: "'HVAC complaints spike every March in Building B' — surface patterns before they become crises.", phase: "v3", competitor: "Johnson Controls, Facilio" },
      { name: "Multi-language support", desc: "Tenant writes in Dutch, AI responds in Dutch. Same model handles EN, NL, PL, DE, FR, ES.", phase: "v2", competitor: "FacilityBot (109 languages)" },
      { name: "Photo/image analysis", desc: "Tenant sends photo of leak/crack. AI adds visual context to ticket: 'water damage visible on ceiling tile'.", phase: "v3", competitor: "Emerging" },
      { name: "Voice input (Whisper)", desc: "Technician in the field records voice note. AI transcribes and creates/updates ticket.", phase: "v3", competitor: "FacilityBot (partial)" },
    ]
  },
  {
    id: "tickets",
    icon: "TK",
    name: "Ticket management",
    desc: "Creating, tracking, resolving issues",
    features: [
      { name: "Auto ticket creation", desc: "Every real maintenance request becomes a ticket with ID, category, priority, timestamp, conversation history.", phase: "mvp", competitor: "All competitors" },
      { name: "Ticket lifecycle", desc: "Status flow: Open → Assigned → In Progress → Resolved → Closed. Each transition timestamped.", phase: "mvp", competitor: "All CMMS" },
      { name: "Conversation thread", desc: "Full chat history attached to each ticket. Manager sees exactly what tenant said and what AI responded.", phase: "mvp", competitor: "FacilityBot" },
      { name: "Tenant status updates", desc: "Automatic notifications when ticket status changes. 'Your HVAC issue has been assigned to a technician.'", phase: "mvp", competitor: "FacilityBot, FaultFixers" },
      { name: "Internal notes", desc: "FM team adds private notes to tickets (not visible to tenant). 'Checked — compressor needs replacement.'", phase: "v2", competitor: "All CMMS" },
      { name: "Photo/file attachments", desc: "Both tenant and technician can attach photos to tickets. Before/after documentation.", phase: "v2", competitor: "All CMMS" },
      { name: "SLA tracking", desc: "Define SLA per priority: Urgent = 2h response, Normal = 24h. Dashboard shows SLA compliance %.", phase: "v2", competitor: "ServiceChannel, Facilio" },
      { name: "Recurring tickets", desc: "Auto-create tickets on schedule: 'Check fire extinguishers monthly' → ticket created on the 1st of each month.", phase: "v3", competitor: "All CMMS (preventive maintenance)" },
      { name: "Vendor/contractor assignment", desc: "Assign tickets to external contractors. Contractor gets email/link, updates status when done.", phase: "v3", competitor: "ServiceChannel, UpKeep" },
    ]
  },
  {
    id: "dashboard",
    icon: "DB",
    name: "Dashboard & analytics",
    desc: "Insights for FM managers",
    features: [
      { name: "Overview stats", desc: "Total tickets, open/resolved, urgent count, avg resolution time — at a glance.", phase: "mvp", competitor: "All competitors" },
      { name: "Ticket table", desc: "Filterable, sortable list of all tickets. Filter by building, category, priority, status, date range.", phase: "mvp", competitor: "All CMMS" },
      { name: "Ticket detail view", desc: "Full conversation, classification, assigned team, timeline of status changes, attachments.", phase: "mvp", competitor: "All CMMS" },
      { name: "Category breakdown", desc: "Pie/bar chart: how many tickets per category. See which systems cause the most problems.", phase: "v2", competitor: "FacilityBot, Facilio" },
      { name: "Trend charts", desc: "Tickets over time — daily, weekly, monthly. Spot seasonal patterns, detect spikes.", phase: "v2", competitor: "FacilityBot, ServiceChannel" },
      { name: "Building comparison", desc: "Compare metrics across buildings. 'Building A has 3x more plumbing issues than B' — actionable insight.", phase: "v2", competitor: "Multi-site CMMS" },
      { name: "Response time analytics", desc: "Avg time to first response, avg time to resolution, by category/building/team.", phase: "v2", competitor: "ServiceChannel, Facilio" },
      { name: "Tenant satisfaction score", desc: "Quick rating after resolution. Track satisfaction over time. Alert on drops.", phase: "v3", competitor: "FacilityBot (surveys)" },
      { name: "CSV/PDF export", desc: "Export tickets to CSV, generate monthly PDF report with charts and metrics.", phase: "mvp", competitor: "All CMMS" },
      { name: "Scheduled email reports", desc: "Weekly digest email to FM manager: 'Last week: 47 tickets, 92% resolved within SLA.'", phase: "v3", competitor: "Facilio, ServiceChannel" },
    ]
  },
  {
    id: "multi",
    icon: "MT",
    name: "Multi-tenant & config",
    desc: "Serving many clients from one platform",
    features: [
      { name: "Client isolation", desc: "Each client's data, documents, tickets 100% separated. Client A never sees Client B's data.", phase: "mvp", competitor: "All SaaS competitors" },
      { name: "Custom branding per client", desc: "Each client gets their own logo, colors, welcome message in the chat widget.", phase: "v2", competitor: "FacilityBot (tenant portal)" },
      { name: "Custom categories per client", desc: "Building A has 'Elevator' category, Building B has 'Parking'. Fully configurable.", phase: "v2", competitor: "Most CMMS" },
      { name: "Custom department routing", desc: "Map categories to departments: 'HVAC → Climate Team', 'Elevator → Schindler Service'.", phase: "v2", competitor: "ServiceChannel" },
      { name: "Multi-building per client", desc: "One client manages 10 buildings. Each building has own docs, own ticket stream, own QR codes.", phase: "v2", competitor: "All multi-site CMMS" },
      { name: "Role-based access", desc: "Admin, Manager, Viewer, Technician roles. Technician sees only assigned tickets.", phase: "v2", competitor: "All CMMS" },
      { name: "Self-serve onboarding", desc: "Client signs up → uploads docs → gets widget code → live in minutes. No developer needed.", phase: "v3", competitor: "FacilityBot" },
      { name: "Custom subdomain", desc: "client1.atrio.ai, client2.atrio.ai — each with their own branding.", phase: "v3", competitor: "FacilityBot" },
      { name: "Bring Your Own API Key", desc: "Client uses their own NVIDIA/OpenAI key. Scales API costs per client, not on you.", phase: "v3", competitor: "Unique differentiator" },
    ]
  },
  {
    id: "integrations",
    icon: "IN",
    name: "Integrations",
    desc: "Connect Atrio to existing tools",
    features: [
      { name: "Email notifications", desc: "Urgent tickets → instant email. Status changes → tenant email. Configurable per client.", phase: "mvp", competitor: "All CMMS" },
      { name: "Slack/Teams webhooks", desc: "Push new tickets and urgent alerts to a Slack/Teams channel.", phase: "v2", competitor: "FacilityBot, Zapier-based" },
      { name: "Zapier/Make integration", desc: "Connect Atrio to 5000+ apps via Zapier. 'New urgent ticket → create Trello card + send SMS.'", phase: "v2", competitor: "FacilityBot (Zapier)" },
      { name: "REST API", desc: "Full public API for developers. Create tickets, read data, build custom integrations.", phase: "v2", competitor: "All serious competitors" },
      { name: "CMMS sync (UpKeep, MaintainX)", desc: "Two-way sync with popular CMMS. Atrio handles AI chat, CMMS handles work order management.", phase: "v3", competitor: "Major differentiator" },
      { name: "Calendar sync (Google, Outlook)", desc: "Scheduled maintenance appears in FM team's calendar. Technician gets calendar invite.", phase: "v3", competitor: "Rare" },
      { name: "IoT sensor integration", desc: "Connect to smart sensors (temperature, humidity, motion). Auto-create tickets on anomalies.", phase: "v3", competitor: "Facilio, Johnson Controls" },
      { name: "BMS integration", desc: "Connect to Building Management Systems. Pull real-time HVAC, lighting, elevator data.", phase: "v3", competitor: "Facilio, Johnson Controls" },
    ]
  },
  {
    id: "tenant",
    icon: "TX",
    name: "Tenant experience",
    desc: "What makes tenants love using Atrio",
    features: [
      { name: "Instant responses 24/7", desc: "No waiting for office hours. Report an issue at 2am Sunday, get acknowledgment in seconds.", phase: "mvp", competitor: "FacilityBot" },
      { name: "No app install needed", desc: "Chat widget, WhatsApp, QR code — tenant uses tools they already have.", phase: "mvp", competitor: "FacilityBot" },
      { name: "Real-time status tracking", desc: "Tenant checks 'What's the status of my AC issue?' → gets live update.", phase: "v2", competitor: "FacilityBot" },
      { name: "Satisfaction survey", desc: "After resolution: 'How was the service? Rate 1-5.' Feeds into analytics.", phase: "v3", competitor: "FacilityBot (surveys)" },
      { name: "FAQ self-service", desc: "Common questions answered instantly from building docs. No ticket needed for 'where is parking?'", phase: "mvp", competitor: "FacilityBot" },
      { name: "Multi-language auto-detect", desc: "Tenant writes in any language. Atrio detects and responds in same language.", phase: "v2", competitor: "FacilityBot" },
      { name: "Facility booking", desc: "Book meeting rooms, hot desks, parking spots through chat. 'Book room A for 2pm tomorrow.'", phase: "v3", competitor: "FacilityBot (core feature)" },
      { name: "Visitor management", desc: "Register visitor via chat. Visitor gets QR code for entry. Host gets notification.", phase: "v3", competitor: "FacilityBot, Wayleadr" },
    ]
  },
  {
    id: "security",
    icon: "SC",
    name: "Security & compliance",
    desc: "Trust, privacy, data protection",
    features: [
      { name: "GDPR compliance", desc: "EU data storage, data processing agreements, right to deletion. Mandatory for NL/EU market.", phase: "mvp", competitor: "Required by law" },
      { name: "Data encryption", desc: "All data encrypted at rest (AES-256) and in transit (TLS 1.3).", phase: "mvp", competitor: "Standard practice" },
      { name: "Audit trail", desc: "Every action logged: who created, changed, deleted, viewed what and when.", phase: "v2", competitor: "FacilityBot, Facilio" },
      { name: "SSO (SAML/OAuth)", desc: "Enterprise clients sign in with their company credentials. No separate Atrio password.", phase: "v3", competitor: "Enterprise CMMS" },
      { name: "Data residency options", desc: "Choose where data is stored: EU, US, or custom region. Selling point for government/healthcare.", phase: "v3", competitor: "Enterprise feature" },
      { name: "SOC 2 compliance", desc: "Audit certification proving security practices. Opens door to enterprise contracts.", phase: "v3", competitor: "Enterprise CMMS" },
    ]
  }
];

const phaseColors = {
  mvp: { bg: "#1E2B4F", color: "#fff", label: "MVP" },
  v2: { bg: "#E07B2A", color: "#fff", label: "v2.0" },
  v3: { bg: "#F5F6F8", color: "#6B7A99", label: "v3.0" },
};

export default function CompetitiveFeatureList() {
  const [activeCat, setActiveCat] = useState("channels");
  const [filterPhase, setFilterPhase] = useState("all");

  const currentCat = categories.find(c => c.id === activeCat);
  const filtered = filterPhase === "all" ? currentCat.features : currentCat.features.filter(f => f.phase === filterPhase);

  const totalByPhase = (phase) => categories.reduce((sum, c) => sum + c.features.filter(f => f.phase === phase).length, 0);

  return (
    <div style={{ fontFamily: "'DM Sans','Segoe UI',system-ui,sans-serif", color: "#141824" }}>
      <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400&display=swap" rel="stylesheet" />

      {/* Header */}
      <div style={{ background: "#1E2B4F", borderRadius: 14, padding: "24px 24px 20px", marginBottom: 16 }}>
        <div style={{ fontSize: 20, fontWeight: 700, color: "#fff", marginBottom: 6 }}>Atrio — competitive feature map</div>
        <p style={{ fontSize: 13, color: "rgba(255,255,255,0.55)", margin: "0 0 16px", lineHeight: 1.5 }}>
          {categories.reduce((s, c) => s + c.features.length, 0)} features across {categories.length} categories. Mapped against FacilityBot, ServiceChannel, Facilio, FexaAI, and others.
        </p>
        <div style={{ display: "flex", gap: 8 }}>
          {[
            { key: "mvp", label: `MVP — ${totalByPhase("mvp")} features` },
            { key: "v2", label: `v2.0 — ${totalByPhase("v2")} features` },
            { key: "v3", label: `v3.0 — ${totalByPhase("v3")} features` },
          ].map(p => (
            <div key={p.key} style={{ background: "rgba(255,255,255,0.1)", borderRadius: 8, padding: "8px 14px" }}>
              <span style={{
                display: "inline-block", padding: "2px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                fontFamily: "'JetBrains Mono',monospace", marginRight: 6,
                background: phaseColors[p.key].bg === "#1E2B4F" ? "rgba(255,255,255,0.2)" : phaseColors[p.key].bg,
                color: "#fff",
              }}>{phaseColors[p.key].label}</span>
              <span style={{ fontSize: 12, color: "rgba(255,255,255,0.7)" }}>{p.label.split("—")[1]}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Category nav */}
      <div style={{ display: "flex", gap: 4, marginBottom: 12, flexWrap: "wrap" }}>
        {categories.map(c => (
          <button key={c.id} onClick={() => setActiveCat(c.id)} style={{
            padding: "6px 14px", borderRadius: 8, border: "none", cursor: "pointer",
            fontSize: 12, fontWeight: 500, fontFamily: "inherit",
            background: activeCat === c.id ? "#1E2B4F" : "#F5F6F8",
            color: activeCat === c.id ? "#fff" : "#6B7A99",
            transition: "all 0.15s",
          }}>
            <span style={{ fontFamily: "'JetBrains Mono',monospace", fontSize: 10, marginRight: 4, opacity: 0.7 }}>{c.icon}</span>
            {c.name}
          </button>
        ))}
      </div>

      {/* Phase filter */}
      <div style={{ display: "flex", gap: 6, marginBottom: 14, alignItems: "center" }}>
        <span style={{ fontSize: 11, color: "#7C8298", marginRight: 4 }}>Show:</span>
        {[
          { key: "all", label: "All" },
          { key: "mvp", label: "MVP only" },
          { key: "v2", label: "v2.0" },
          { key: "v3", label: "v3.0" },
        ].map(f => (
          <button key={f.key} onClick={() => setFilterPhase(f.key)} style={{
            padding: "4px 12px", borderRadius: 6, border: "1px solid",
            borderColor: filterPhase === f.key ? "#1E2B4F" : "#E0E2E8",
            background: filterPhase === f.key ? "#EAECF2" : "#fff",
            color: filterPhase === f.key ? "#1E2B4F" : "#7C8298",
            fontSize: 11, fontWeight: 500, fontFamily: "inherit", cursor: "pointer",
          }}>{f.label}</button>
        ))}
      </div>

      {/* Category header */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 16, fontWeight: 600, color: "#1E2B4F" }}>{currentCat.name}</div>
        <div style={{ fontSize: 13, color: "#6B7A99" }}>{currentCat.desc} — {filtered.length} features</div>
      </div>

      {/* Feature list */}
      {filtered.map((f, i) => {
        const p = phaseColors[f.phase];
        return (
          <div key={i} style={{
            background: "#fff", border: "1px solid #E0E2E8", borderRadius: 10,
            padding: "14px 16px", marginBottom: 8,
          }}>
            <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
              <span style={{
                display: "inline-block", padding: "3px 8px", borderRadius: 5,
                fontSize: 10, fontWeight: 600, fontFamily: "'JetBrains Mono',monospace",
                background: p.bg, color: p.color, flexShrink: 0, marginTop: 2,
                letterSpacing: 0.3,
              }}>{p.label}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600, color: "#141824", marginBottom: 3 }}>{f.name}</div>
                <div style={{ fontSize: 12, color: "#6B7A99", lineHeight: 1.6, marginBottom: 6 }}>{f.desc}</div>
                <div style={{ fontSize: 11, color: "#9EA3B5" }}>
                  Competitors: <span style={{ color: "#7C8298" }}>{f.competitor}</span>
                </div>
              </div>
            </div>
          </div>
        );
      })}

      {filtered.length === 0 && (
        <div style={{ background: "#F5F6F8", borderRadius: 10, padding: 20, textAlign: "center", color: "#7C8298", fontSize: 13 }}>
          No features in this category for the selected phase.
        </div>
      )}
    </div>
  );
}
