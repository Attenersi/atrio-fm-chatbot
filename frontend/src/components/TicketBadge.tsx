export function TicketBadge({ label }: { label: string }) {
  const colorMap: Record<string, string> = {
    // Priority
    URGENT: "#b42318",
    HIGH: "#b54708",
    NORMAL: "#175cd3",
    LOW: "#067647",
    // Category
    HVAC: "#0e7090",
    Electrical: "#7a5af8",
    Plumbing: "#175cd3",
    Safety: "#b42318",
    General: "#667085",
    // Query type
    INFORMATIONAL: "#667085",
    SERVICE_REQUEST: "#175cd3",
    "SERVICE REQUEST": "#175cd3",
    INCIDENT: "#b42318",
    OUT_OF_SCOPE: "#344054",
    "OUT OF SCOPE": "#344054",
  };
  const color = colorMap[label] ?? "#667085";
  return (
    <span
      className="badge"
      style={{
        background: `${color}18`,
        color,
        border: `1px solid ${color}55`,
        letterSpacing: 0.2,
        fontFamily: "'JetBrains Mono', monospace",
      }}
    >
      {label}
    </span>
  );
}
