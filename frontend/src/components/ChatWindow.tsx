"use client";

import { FormEvent, useEffect, useState } from "react";
import { createManualTicket, getChatHistory, startNewChat, streamChat, type ChatHistoryItem } from "../lib/api";
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
  sources?: string[];
};

export function ChatWindow() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [creatingTicketIdx, setCreatingTicketIdx] = useState<number | null>(null);

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
    const nextMessages = [...messages, { role: "user" as const, text: userText }];
    setMessages(nextMessages);
    setLoading(true);

    try {
      const history: ChatHistoryItem[] = messages
        .slice(-12)
        .map((m) => ({
          role: m.role === "bot" ? "assistant" : "user",
          content: m.text,
        }));
      const streamIndex = nextMessages.length;
      setMessages([
        ...nextMessages,
        {
          role: "bot",
          text: "",
        },
      ]);
      let streamedText = "";
      const result = await streamChat(userText, history, (delta) => {
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
                sources: result.used_sources ?? [],
              }
            : item
        )
      );
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: "bot", text: "Error contacting backend." },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function startNewChat() {
    if (loading) return;
    void (async () => {
      try {
        await startNewChat();
        setMessages([]);
        setInput("");
      } catch {
        setMessages((prev) => [...prev, { role: "bot", text: "Could not start a new chat. Please try again." }]);
      }
    })();
  }

  async function createTicketAnyway(index: number) {
    const msg = messages[index];
    if (!msg || msg.role !== "bot" || msg.ticketId || !msg.sourceMessage) return;
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
        { role: "bot", text: "Could not create manual ticket. Please try again." },
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
              sources={m.sources}
              onCreateTicketAnyway={
                m.role === "bot" && m.ticketCreated === false ? () => createTicketAnyway(i) : undefined
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
          onClick={startNewChat}
          disabled={loading}
          className="btn btn-ghost"
        >
          New chat
        </button>
        <button
          type="submit"
          disabled={loading}
          className="btn btn-primary"
        >
          {loading ? "Sending..." : "Send"}
        </button>
      </form>
    </section>
  );
}
