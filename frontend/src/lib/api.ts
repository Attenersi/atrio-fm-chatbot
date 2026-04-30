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

export async function streamChat(
  message: string,
  onChunk: (delta: string) => void
) {
  // Server reads chat history from the DB; we intentionally do not send it
  // from the client to keep a single source of truth.
  const res = await fetch(`${API_URL}/api/chat/stream`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok || !res.body) {
    if (res.status === 401) {
      throw new Error("Not signed in (401). Open /login and sign in again.");
    }
    let detail = "";
    try {
      const body = await res.json();
      if (typeof (body as { detail?: string })?.detail === "string") {
        detail = ` — ${(body as { detail: string }).detail}`;
      }
    } catch {
      /* ignore */
    }
    throw new Error(`Request failed: ${res.status}${detail}`);
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
        const err = new Error(String(evt.message ?? "Streaming failed"));
        // Tag partial errors so the UI can preserve already-streamed text.
        (err as Error & { partial?: boolean }).partial = Boolean(evt.partial);
        throw err;
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

export async function apiStartNewChatThread() {
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

export type TrainingQualityGroup = {
  type: string;
  count: number;
  rag_signal: boolean;
  affected_ids: number[];
  examples_preview: Array<{
    id: number;
    input_excerpt: string;
    expected: Record<string, any>;
    actual: Record<string, any>;
    source_type: string;
  }>;
};

export type TrainingQualityGroups = {
  total_pending: number;
  groups: TrainingQualityGroup[];
  generated_at: string;
};

export async function adminGetTrainingQualityGroups(limitPerGroup = 5) {
  return req(
    `/api/admin/training-quality/groups?limit_per_group=${limitPerGroup}`,
  ) as Promise<TrainingQualityGroups>;
}

export type EvalRunSummary = {
  id: number;
  status: "running" | "done" | "error";
  total: number;
  passed: number;
  accuracy_overall: number | null;
  accuracy_category: number | null;
  accuracy_priority: number | null;
  accuracy_ticket_created: number | null;
  accuracy_response_tokens: number | null;
  started_at: string;
  finished_at: string | null;
  prompt_override_active_ids: number[];
};

export type EvalRunDetails = EvalRunSummary & {
  details: { elapsed_seconds?: number; failures?: Array<{ case_id: string; failures: string[]; error: string | null }>; error?: string };
};

export async function adminStartEvalRun() {
  return req("/api/admin/training-quality/eval/run", { method: "POST" }) as Promise<{
    run_id: number;
    status: string;
  }>;
}

export async function adminListEvalRuns(limit = 20) {
  return req(`/api/admin/training-quality/eval/runs?limit=${limit}`) as Promise<{
    runs: EvalRunSummary[];
  }>;
}

export async function adminGetEvalRun(runId: number) {
  return req(`/api/admin/training-quality/eval/runs/${runId}`) as Promise<{
    run: EvalRunDetails;
  }>;
}

export type AnalyzerGroup = {
  type: string;
  suggested_change: string;
  rationale: string;
  confidence: number;
  affected_ids: number[];
};

export type AnalyzerRagSuggestion = {
  type: string;
  description: string;
  affected_ids: number[];
};

export type AnalyzerPayload = {
  cached: boolean;
  cache_key: string;
  generated_at: string | null;
  model: string | null;
  groups: AnalyzerGroup[];
  rag_suggestions: AnalyzerRagSuggestion[];
};

export async function adminGetTrainingQualityAnalysis() {
  return req("/api/admin/training-quality/analysis") as Promise<AnalyzerPayload>;
}

export type PromptOverride = {
  id: number;
  error_type: string;
  suggested_change: string;
  approved_change: string;
  status: "pending" | "active" | "rejected" | "superseded";
  affected_example_ids: number[];
  created_by_user_id: number | null;
  created_at: string;
  activated_at: string | null;
  deactivated_at: string | null;
  eval_baseline_id: number | null;
  eval_after_id: number | null;
  baseline_accuracy: number | null;
  after_accuracy: number | null;
};

export async function adminListPromptOverrides(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return req(`/api/admin/training-quality/overrides${qs}`) as Promise<{
    overrides: PromptOverride[];
  }>;
}

export async function adminApplyPromptOverride(payload: {
  error_type: string;
  suggested_change?: string;
  approved_change: string;
  affected_example_ids: number[];
  confidence?: number;
  manually_edited?: boolean;
}) {
  return req("/api/admin/training-quality/overrides/apply", {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<{
    override: PromptOverride;
    baseline: { id: number; accuracy_overall: number | null };
    eval_after_run_id: number | null;
  }>;
}

export async function adminRollbackPromptOverride(overrideId: number) {
  return req(
    `/api/admin/training-quality/overrides/${overrideId}/rollback`,
    { method: "POST" },
  ) as Promise<{ override: PromptOverride }>;
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
