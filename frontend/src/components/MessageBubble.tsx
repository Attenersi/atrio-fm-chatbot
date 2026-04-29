import { TicketBadge } from "./TicketBadge";

export function MessageBubble({
  role,
  text,
  category,
  priority,
  queryType,
  ticketCreated,
  ticketId,
  sources,
  onCreateTicketAnyway,
  creatingTicket,
}: {
  role: "user" | "bot";
  text: string;
  category?: string;
  priority?: string;
  queryType?: "INFORMATIONAL" | "SERVICE_REQUEST" | "INCIDENT" | "OUT_OF_SCOPE";
  ticketCreated?: boolean;
  ticketId?: number | null;
  sources?: string[];
  onCreateTicketAnyway?: () => void;
  creatingTicket?: boolean;
}) {
  const isUser = role === "user";
  return (
    <div
      style={{
        maxWidth: "80%",
        marginLeft: isUser ? "auto" : 0,
        marginBottom: 10,
      }}
    >
      <div
        className="card"
        style={{
          background: isUser ? "var(--color-chat-user-bg)" : "var(--color-chat-bot-bg)",
          color: isUser ? "var(--color-chat-user-fg)" : "var(--color-chat-bot-fg)",
          padding: 12,
        }}
      >
        <div>{text}</div>
        {!isUser && (
          <>
            <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
              {category ? <TicketBadge label={category} /> : null}
              {priority ? <TicketBadge label={priority} /> : null}
              {queryType ? <TicketBadge label={queryType.replaceAll("_", " ")} /> : null}
            </div>
            {ticketId ? (
              <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--chip-info-text)", fontWeight: 700 }}>
                Ticket created: #{ticketId}
              </p>
            ) : null}
            {ticketCreated === false ? (
              <div style={{ marginTop: 8, display: "grid", gap: 8 }}>
                <p style={{ margin: 0, fontSize: 12, color: "var(--muted)" }}>
                  Informational query - no ticket created automatically.
                </p>
                {onCreateTicketAnyway ? (
                  <button
                    type="button"
                    onClick={onCreateTicketAnyway}
                    disabled={creatingTicket}
                    className="btn btn-ghost"
                    style={{ width: "fit-content", fontSize: 12, padding: "6px 10px" }}
                  >
                    {creatingTicket ? "Creating..." : "Create ticket anyway"}
                  </button>
                ) : null}
              </div>
            ) : null}
            {sources && sources.length > 0 ? (
              <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--muted)" }}>
                Sources: {sources.join(", ")}
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
