export function TicketBadge({ label }: { label: string }) {
  const toneMap: Record<string, "danger" | "warn" | "info" | "success" | "neutral"> = {
    URGENT: "danger",
    HIGH: "warn",
    NORMAL: "info",
    LOW: "success",
    HVAC: "info",
    Electrical: "info",
    Plumbing: "info",
    Safety: "danger",
    General: "neutral",
    INFORMATIONAL: "neutral",
    SERVICE_REQUEST: "info",
    "SERVICE REQUEST": "info",
    INCIDENT: "danger",
    OUT_OF_SCOPE: "neutral",
    "OUT OF SCOPE": "neutral",
  };
  const tone = toneMap[label] ?? "neutral";
  const toneStyle: Record<string, React.CSSProperties> = {
    danger: {
      background: "var(--chip-danger-bg)",
      color: "var(--chip-danger-text)",
      border: "1px solid var(--chip-danger-border)",
    },
    warn: {
      background: "var(--chip-warn-bg)",
      color: "var(--chip-warn-text)",
      border: "1px solid var(--chip-warn-border)",
    },
    info: {
      background: "var(--chip-info-bg)",
      color: "var(--chip-info-text)",
      border: "1px solid var(--chip-info-border)",
    },
    success: {
      background: "var(--chip-success-bg)",
      color: "var(--chip-success-text)",
      border: "1px solid var(--chip-success-border)",
    },
    neutral: {
      background: "var(--chip-neutral-bg)",
      color: "var(--chip-neutral-text)",
      border: "1px solid var(--chip-neutral-border)",
    },
  };
  return (
    <span
      className="badge"
      style={{
        ...toneStyle[tone],
        letterSpacing: 0.2,
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      {label}
    </span>
  );
}
