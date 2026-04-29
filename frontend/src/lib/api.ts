const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

export type ChatResponse = {
  category: string;
  priority: string;
  department: string;
  response: string;
  issue_summary: string;
  context_count: number;
  used_sources?: string[];
  query_type: "INFORMATIONAL" | "SERVICE_REQUEST" | "INCIDENT" | "OUT_OF_SCOPE";
  ticket_created: boolean;
  ticket_id: number | null;
};

export type Ticket = {
  id: number;
  message: string;
  issue_summary: string;
  category: string;
  priority: string;
  department: string;
  response: string;
  status: string;
  created_by_user_id: number | null;
  created_by_username?: string | null;
  created_at: string;
};

export type AuthUser = {
  id: number;
  username: string;
  role: "admin" | "user";
  email?: string | null;
};

export type AdminUserRow = {
  id: number;
  username: string;
  role: "admin" | "user";
  is_active: number;
  created_at: string;
  email: string | null;
};

export type ChatHistoryItem = {
  role: "user" | "assistant";
  content: string;
};

export type ChatStoredMessage = {
  id: number;
  thread_id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type TicketFilters = {
  category?: string;
  priority?: string;
  status?: string;
};

export type AdminDoc = {
  name: string;
  size_bytes: number;
};

export type KnowledgeGap = {
  id: number;
  question: string;
  ticket_id: number | null;
  category: string;
  response: string;
  status: "new" | "reviewed" | "resolved";
  notes: string;
  created_at: string;
  resolved_at: string | null;
};

export type TrainingExample = {
  id: number;
  input_text: string;
  actual_output: {
    category?: string;
    priority?: string;
    create_ticket?: boolean;
    response?: string;
    issue_summary?: string;
    [key: string]: any;
  };
  ideal_output: {
    category?: string;
    priority?: string;
    create_ticket?: boolean;
    response?: string;
    issue_summary?: string;
    [key: string]: any;
  };
  human_notes: string;
  correction_type: "pending" | "approved" | "edited" | "rejected";
  context_used: string[];
  reasoning: string;
  used_sources: string[];
  context_count: number;
  query_type: string;
  in_scope: string;
  grounded: string;
  ticket_created: boolean;
  ticket_id: number | null;
  user_id: number | null;
  user_role: string;
  model: string;
  run_id: string;
  knowledge_gap_logged: boolean;
  knowledge_gap_reason: string;
  created_at: string;
  reviewed_at: string | null;
};

export type ResolutionNote = {
  id: number;
  ticket_id: number;
  note: string;
  added_by: string;
  parts_used: string;
  cost: number | null;
  time_spent_minutes: number | null;
  created_at: string;
};

export type ClassificationOverride = {
  id: number;
  ticket_id: number;
  field_changed: "category" | "priority" | "department";
  ai_value: string;
  manager_value: string;
  changed_by: string;
  created_at: string;
};

async function req(path: string, init?: RequestInit) {
  const hasFormDataBody = init?.body instanceof FormData;
  const baseHeaders: HeadersInit = hasFormDataBody
    ? {}
    : { "Content-Type": "application/json" };
  const mergedHeaders: HeadersInit = {
    ...baseHeaders,
    ...(init?.headers ?? {}),
  };
  const res = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    ...init,
    headers: mergedHeaders,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      }
    } catch {
      detail = "";
    }
    throw new Error(`Request failed: ${res.status}${detail ? ` - ${detail}` : ""}`);
  }
  return res.json();
}

export async function sendChat(message: string, history: ChatHistoryItem[] = []) {
  return req("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message, history }),
  }) as Promise<ChatResponse>;
}

export async function streamChat(
  message: string,
  history: ChatHistoryItem[],
  onChunk: (delta: string) => void
) {
  const res = await fetch(`${API_URL}/api/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
  if (!res.ok || !res.body) {
    throw new Error(`Request failed: ${res.status}`);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalPayload: ChatResponse | null = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const rawEvent of events) {
      const line = rawEvent
        .split("\n")
        .find((l) => l.startsWith("data: "));
      if (!line) continue;
      const jsonStr = line.slice(6);
      let evt: any;
      try {
        evt = JSON.parse(jsonStr);
      } catch {
        continue;
      }
      if (evt.type === "chunk") {
        onChunk(String(evt.delta ?? ""));
      } else if (evt.type === "final") {
        finalPayload = evt.payload as ChatResponse;
      } else if (evt.type === "error") {
        throw new Error(String(evt.message ?? "Streaming failed"));
      }
    }
  }
  if (!finalPayload) {
    throw new Error("Streaming finished without final payload");
  }
  return finalPayload;
}

export async function getChatHistory(limit = 200) {
  return req(`/api/chat/history?limit=${Math.max(1, Math.min(2000, limit))}`) as Promise<{
    thread: { id: number; user_id: number; is_active: boolean; title: string; created_at: string; updated_at: string };
    messages: ChatStoredMessage[];
  }>;
}

export async function startNewChat() {
  return req("/api/chat/new", { method: "POST" }) as Promise<{
    thread: { id: number; user_id: number; is_active: boolean; title: string; created_at: string; updated_at: string };
  }>;
}

export async function getTickets(filters?: TicketFilters) {
  const params = new URLSearchParams();
  if (filters?.category) params.set("category", filters.category);
  if (filters?.priority) params.set("priority", filters.priority);
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return req(`/api/tickets${qs ? `?${qs}` : ""}`);
}

export async function getTicketById(ticketId: number) {
  return req(`/api/tickets/${ticketId}`) as Promise<{ ticket: Ticket }>;
}

export async function getStats() {
  return req("/api/tickets/stats");
}

export async function updateTicketStatus(ticketId: number, status: string) {
  return req(`/api/tickets/${ticketId}`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
}

export async function createManualTicket(payload: {
  message: string;
  issue_summary: string;
  category?: string;
  priority?: string;
  department?: string;
  response?: string;
}) {
  return req("/api/tickets/manual", {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<{ ticket: Ticket }>;
}

export async function adminLogin(username: string, password: string) {
  return req("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  }) as Promise<{ authenticated: boolean; user: AuthUser }>;
}

export async function adminLogout() {
  return req("/api/auth/logout", {
    method: "POST",
  }) as Promise<{ authenticated: boolean }>;
}

export async function adminSession() {
  return req("/api/auth/session") as Promise<{ authenticated: boolean; user: AuthUser }>;
}

export const login = adminLogin;
export const logout = adminLogout;
export const getSession = adminSession;
export async function register(username: string, password: string) {
  return req("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  }) as Promise<{ created: boolean; user: AuthUser }>;
}

export async function adminListUsers() {
  return req("/api/admin/users") as Promise<{ users: AdminUserRow[] }>;
}

export async function adminUpdateUser(
  userId: number,
  body: { role?: "admin" | "user"; is_active?: boolean; email?: string | null }
) {
  return req(`/api/admin/users/${userId}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  }) as Promise<{ user: AdminUserRow }>;
}

export async function adminListDocs() {
  return req("/api/admin/docs") as Promise<{ docs: AdminDoc[] }>;
}

export async function adminGetDoc(name: string) {
  return req(`/api/admin/docs/${encodeURIComponent(name)}`) as Promise<{ name: string; content: string }>;
}

export async function adminCreateDoc(name: string, content: string) {
  return req("/api/admin/docs", {
    method: "POST",
    body: JSON.stringify({ name, content }),
  }) as Promise<{ created: boolean; name: string }>;
}

export async function adminUpdateDoc(name: string, content: string) {
  return req(`/api/admin/docs/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify({ content }),
  }) as Promise<{ updated: boolean; name: string }>;
}

export async function adminDeleteDoc(name: string) {
  return req(`/api/admin/docs/${encodeURIComponent(name)}`, {
    method: "DELETE",
  }) as Promise<{ deleted: boolean; name: string }>;
}

export async function adminReindex() {
  return req("/api/admin/reindex", {
    method: "POST",
  }) as Promise<{ chunks_indexed: number }>;
}

export async function adminUploadDoc(
  file: File,
  overwrite = true,
  autoReindex = false
) {
  const body = new FormData();
  body.append("file", file);
  body.append("overwrite", String(overwrite));
  body.append("auto_reindex", String(autoReindex));
  return req("/api/admin/upload", {
    method: "POST",
    body,
  }) as Promise<{
    uploaded: boolean;
    source_filename: string;
    saved_as: string;
    chars: number;
    auto_reindexed: boolean;
    chunks_indexed: number | null;
  }>;
}

export async function adminListKnowledgeGaps(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return req(`/api/admin/knowledge-gaps${qs}`) as Promise<{ gaps: KnowledgeGap[] }>;
}

export async function adminUpdateKnowledgeGap(
  gapId: number,
  status: "new" | "reviewed" | "resolved",
  notes?: string
) {
  return req(`/api/admin/knowledge-gaps/${gapId}`, {
    method: "PATCH",
    body: JSON.stringify({ status, notes }),
  }) as Promise<{ gap: KnowledgeGap }>;
}

export async function adminGetKnowledgeGap(gapId: number) {
  return req(`/api/admin/knowledge-gaps/${gapId}`) as Promise<{ gap: KnowledgeGap }>;
}

export async function adminResolveKnowledgeGap(
  gapId: number,
  payload: {
    doc_name: string;
    category: string;
    content: string;
    mode: "append" | "overwrite";
    auto_reindex: boolean;
  }
) {
  return req(`/api/admin/knowledge-gaps/${gapId}/resolve`, {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<{ gap: KnowledgeGap; saved_doc: string; chunks_indexed: number | null }>;
}

export async function adminListTrainingExamples(filters?: {
  correction_type?: string;
  user_role?: string;
  limit?: number;
  offset?: number;
}) {
  const params = new URLSearchParams();
  if (filters?.correction_type) params.set("correction_type", filters.correction_type);
  if (filters?.user_role) params.set("user_role", filters.user_role);
  if (typeof filters?.limit === "number") params.set("limit", String(filters.limit));
  if (typeof filters?.offset === "number") params.set("offset", String(filters.offset));
  const qs = params.toString();
  return req(`/api/admin/training-examples${qs ? `?${qs}` : ""}`) as Promise<{ examples: TrainingExample[] }>;
}

export async function adminGetTrainingExample(exampleId: number) {
  return req(`/api/admin/training-examples/${exampleId}`) as Promise<{ example: TrainingExample }>;
}

export async function adminUpdateTrainingExample(
  exampleId: number,
  payload: {
    correction_type: "pending" | "approved" | "edited" | "rejected";
    ideal_output?: Record<string, any> | null;
    human_notes?: string | null;
    context_used?: string[] | null;
    reasoning?: string | null;
  }
) {
  return req(`/api/admin/training-examples/${exampleId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  }) as Promise<{ example: TrainingExample }>;
}

export async function adminExportTrainingExamples(correctionTypes = "approved,edited") {
  const res = await fetch(
    `${API_URL}/api/admin/training-examples/export?correction_types=${encodeURIComponent(correctionTypes)}`,
    { credentials: "include" }
  );
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.text();
}

export async function adminGetTrainingV1Manifest() {
  return req("/api/admin/training-examples/v1/manifest") as Promise<Record<string, any>>;
}

export async function adminExportTrainingV1Jsonl() {
  const res = await fetch(`${API_URL}/api/admin/training-examples/v1/export-jsonl`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.text();
}

export async function adminExportTrainingV1Csv() {
  const res = await fetch(`${API_URL}/api/admin/training-examples/v1/export-csv`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.text();
}

export async function adminBuildTrainingV1Files(payload?: { test_results_path?: string; output_dir?: string }) {
  return req("/api/admin/training-examples/v1/build-files", {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  }) as Promise<Record<string, any>>;
}

export async function adminListResolutionNotes(ticketId: number) {
  return req(`/api/admin/tickets/${ticketId}/resolution-notes`) as Promise<{
    notes: ResolutionNote[];
  }>;
}

export async function adminCreateResolutionNote(
  ticketId: number,
  payload: {
    note: string;
    added_by?: string;
    parts_used?: string;
    cost?: number | null;
    time_spent_minutes?: number | null;
  }
) {
  return req(`/api/admin/tickets/${ticketId}/resolution-notes`, {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<{ note: ResolutionNote }>;
}

export async function adminListClassificationOverrides(ticketId: number) {
  return req(`/api/admin/tickets/${ticketId}/classification-overrides`) as Promise<{
    overrides: ClassificationOverride[];
  }>;
}

export async function adminCreateClassificationOverride(
  ticketId: number,
  payload: {
    field_changed: "category" | "priority" | "department";
    manager_value: string;
    changed_by?: string;
  }
) {
  return req(`/api/admin/tickets/${ticketId}/classification-overrides`, {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<{
    ticket: Ticket;
    override: ClassificationOverride;
    training_examples_updated: number;
  }>;
}
