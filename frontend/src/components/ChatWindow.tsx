"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  apiStartNewChatThread,
  createManualTicket,
  getChatHistory,
  streamChat,
} from "../lib/api";
import { MessageBubble } from "./MessageBubble";

type ChatMessage = {
  role: "user" | "bot";
  text: string;
  sourceMessage?: string;
  issueSummary?: string;
  category?: string;
  priority?: string;
  queryType?: "INFORMATIONAL" | "SERVICE_REQUEST" | "INCIDENT" | "OUT_OF_SCOPE";
  ticketCreated?: boolean;
  ticketId?: number | null;
  ticketIds?: number[];
  sources?: string[];
};

export function ChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [creatingTicketIdx, setCreatingTicketIdx] = useState<number | null>(
    null
  );

  useEffect(() => {
    void (async () => {
      try {
        const res = await getChatHistory(200);
        const mapped: ChatMessage[] = (res.messages || []).map((m) => ({
          role: m.role === "assistant" ? "bot" : "user",
          text: m.content,
        }));
        setMessages(mapped);
      } catch {
        setMessages([]);
      } finally {
        setHistoryLoading(false);
      }
    })();
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userText = input.trim();
    setInput("");
    const nextMessages = [
      ...messages,
      { role: "user" as const, text: userText },
    ];
    setMessages(nextMessages);
    setLoading(true);

    try {
      // Backend reads chat history from the DB on every turn, so we don't
      // need to ship a copy from the client. Fewer bytes, fewer ways to
      // diverge from server-side state.
      const streamIndex = nextMessages.length;
      setMessages([
        ...nextMessages,
        {
          role: "bot",
          text: "",
        },
      ]);
      let streamedText = "";
      const result = await streamChat(userText, (delta) => {
        streamedText += delta;
        setMessages((prev) =>
          prev.map((item, idx) =>
            idx === streamIndex ? { ...item, text: streamedText } : item
          )
        );
      });
      setMessages((prev) =>
        prev.map((item, idx) =>
          idx === streamIndex
            ? {
                ...item,
                text: result.response || streamedText,
                sourceMessage: userText,
                issueSummary: result.issue_summary,
                category: result.category,
                priority: result.priority,
                queryType: result.query_type,
                ticketCreated: result.ticket_created,
                ticketId: result.ticket_id,
                ticketIds: result.ticket_ids?.length
                  ? result.ticket_ids
                  : undefined,
                sources: result.used_sources ?? [],
              }
            : item
        )
      );
    } catch (err) {
      const detail = err instanceof Error ? err.message : String(err);
      const partial = Boolean((err as Error & { partial?: boolean })?.partial);
      const hint =
        /failed to fetch|networkerror|load failed/i.test(detail) &&
        typeof window !== "undefined" &&
        window.location.hostname !== "localhost" &&
        window.location.hostname !== "127.0.0.1"
          ? " If this device is not the machine running the API, set NEXT_PUBLIC_API_URL to the backend URL (same host as this page) and restart Next.js."
          : "";
      const message = `Error contacting backend: ${detail}${hint}`.slice(
        0,
        1200
      );
      if (partial) {
        // Append error to the in-flight bot bubble so the user sees one
        // continuous turn instead of "half answer + new error bubble".
        setMessages((prev) => {
          if (prev.length === 0) {
            return [...prev, { role: "bot", text: message }];
          }
          const last = prev[prev.length - 1];
          if (last.role !== "bot") {
            return [...prev, { role: "bot", text: message }];
          }
          const merged = `${last.text}\n\n${message}`.slice(0, 4000);
          return prev.map((item, idx) =>
            idx === prev.length - 1 ? { ...item, text: merged } : item
          );
        });
      } else {
        setMessages((prev) => [...prev, { role: "bot", text: message }]);
      }
    } finally {
      setLoading(false);
    }
  }

  function handleStartNewChat() {
    if (loading) return;
    void (async () => {
      try {
        await apiStartNewChatThread();
        setMessages([]);
        setInput("");
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            role: "bot",
            text: "Could not start a new chat. Please try again.",
          },
        ]);
      }
    })();
  }

  async function createTicketAnyway(index: number) {
    const msg = messages[index];
    if (!msg || msg.role !== "bot" || msg.ticketId || !msg.sourceMessage)
      return;
    setCreatingTicketIdx(index);
    try {
      const res = await createManualTicket({
        message: msg.sourceMessage,
        issue_summary: msg.issueSummary ?? msg.sourceMessage,
        category: msg.category ?? "General",
        priority: msg.priority ?? "NORMAL",
        department: "Facility Management",
        response: msg.text,
      });
      setMessages((prev) =>
        prev.map((item, i) =>
          i === index
            ? {
                ...item,
                ticketCreated: true,
                ticketId: res.ticket.id,
              }
            : item
        )
      );
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "bot",
          text: "Could not create manual ticket. Please try again.",
        },
      ]);
    } finally {
      setCreatingTicketIdx(null);
    }
  }

  return (
    <section className="page-shell">
      <div className="toolbar" style={{ justifyContent: "space-between" }}>
        <h1 style={{ margin: 0 }}>FM Assistant Chat</h1>
      </div>
      <div className="card" style={{ minHeight: 360, marginBottom: 12 }}>
        {historyLoading ? (
          <p>Loading chat history...</p>
        ) : messages.length === 0 ? (
          <p>Ask a facilities question or report a maintenance issue.</p>
        ) : (
          messages.map((m, i) => (
            <MessageBubble
              key={i}
              role={m.role}
              text={m.text}
              category={m.category}
              priority={m.priority}
              queryType={m.queryType}
              ticketCreated={m.ticketCreated}
              ticketId={m.ticketId}
              ticketIds={m.ticketIds}
              sources={m.sources}
              onCreateTicketAnyway={
                m.role === "bot" && m.ticketCreated === false
                  ? () => createTicketAnyway(i)
                  : undefined
              }
              creatingTicket={creatingTicketIdx === i}
            />
          ))
        )}
      </div>
      <form onSubmit={onSubmit} style={{ display: "flex", gap: 8 }}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Type your message..."
          className="field"
          style={{ flex: 1 }}
        />
        <button
          type="button"
          onClick={handleStartNewChat}
          disabled={loading}
          className="btn btn-ghost"
        >
          New chat
        </button>
        <button type="submit" disabled={loading} className="btn btn-primary">
          {loading ? "Sending..." : "Send"}
        </button>
      </form>
    </section>
  );
}
