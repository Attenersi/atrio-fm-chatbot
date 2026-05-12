const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  /** When the user reported multiple separate problems in one message. */
  ticket_ids?: number[];
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
      } else if (body?.detail) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      detail = "";
    }
    throw new Error(
      `Request failed: ${res.status}${detail ? ` - ${detail}` : ""}`
    );
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
      const line = rawEvent.split("\n").find((l) => l.startsWith("data: "));
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
  return req(
    `/api/chat/history?limit=${Math.max(1, Math.min(2000, limit))}`
  ) as Promise<{
    thread: {
      id: number;
      user_id: number;
      is_active: boolean;
      title: string;
      created_at: string;
      updated_at: string;
    };
    messages: ChatStoredMessage[];
  }>;
}

export async function apiStartNewChatThread() {
  return req("/api/chat/new", { method: "POST" }) as Promise<{
    thread: {
      id: number;
      user_id: number;
      is_active: boolean;
      title: string;
      created_at: string;
      updated_at: string;
    };
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
  return req("/api/auth/session") as Promise<{
    authenticated: boolean;
    user: AuthUser;
  }>;
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
  return req(`/api/admin/docs/${encodeURIComponent(name)}`) as Promise<{
    name: string;
    content: string;
  }>;
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

export type IngestPreChunkOptions = {
  docs_dir: string;
  chroma_dir: string;
  sanitize_instruction_like: boolean;
  text_splitter_separators: string[];
  chunk_metadata_keyword_limit: number;
  chroma_collection: string;
  embed_input_type_for_passages: string;
};

export type RagTopKAdminDetail = {
  effective: number;
  env_startup_default: number;
  meta_override_active: boolean;
  limits: { min: number; max: number };
};

export type AdminReindexDefaults = {
  ingest_chunk_size: number;
  ingest_chunk_overlap: number;
  rag_top_k: number;
  rag_top_k_env_startup_default: number;
  rag_top_k_meta_override_active: boolean;
  rag_top_k_limits: { min: number; max: number };
  limits: {
    chunk_size_min: number;
    chunk_size_max: number;
    chunk_overlap_min: number;
  };
  ingest_pre_chunk: IngestPreChunkOptions;
};

export async function adminReindexDefaults() {
  return req("/api/admin/reindex/defaults") as Promise<AdminReindexDefaults>;
}

export type AdminRagSettingsResponse = {
  rag_top_k: RagTopKAdminDetail;
  ingest_pre_chunk: IngestPreChunkOptions;
  ingest_chunk_defaults: { chunk_size: number; chunk_overlap: number };
};

export async function adminPatchRagSettings(body: {
  rag_top_k?: number;
  clear_rag_top_k_override?: boolean;
}) {
  // POST (not PATCH): some proxies return 404 for PATCH; behavior is identical on the server.
  return req("/api/admin/rag/settings", {
    method: "POST",
    body: JSON.stringify(body),
  }) as Promise<AdminRagSettingsResponse>;
}

export async function adminReindex(opts?: {
  chunk_size?: number;
  chunk_overlap?: number;
}) {
  const params = new URLSearchParams();
  if (typeof opts?.chunk_size === "number")
    params.set("chunk_size", String(opts.chunk_size));
  if (typeof opts?.chunk_overlap === "number")
    params.set("chunk_overlap", String(opts.chunk_overlap));
  const qs = params.toString();
  return req(`/api/admin/reindex${qs ? `?${qs}` : ""}`, {
    method: "POST",
  }) as Promise<{
    chunks_indexed: number;
    chunk_size: number;
    chunk_overlap: number;
  }>;
}

export async function adminUploadDoc(
  file: File,
  overwrite = true,
  autoReindex = false,
  ingestChunks?: { chunk_size?: number; chunk_overlap?: number }
) {
  const body = new FormData();
  body.append("file", file);
  body.append("overwrite", String(overwrite));
  body.append("auto_reindex", String(autoReindex));
  if (typeof ingestChunks?.chunk_size === "number") {
    body.append("chunk_size", String(ingestChunks.chunk_size));
  }
  if (typeof ingestChunks?.chunk_overlap === "number") {
    body.append("chunk_overlap", String(ingestChunks.chunk_overlap));
  }
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
    chunk_size: number | null;
    chunk_overlap: number | null;
  }>;
}

export async function adminListKnowledgeGaps(status?: string) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return req(`/api/admin/knowledge-gaps${qs}`) as Promise<{
    gaps: KnowledgeGap[];
  }>;
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
  return req(`/api/admin/knowledge-gaps/${gapId}`) as Promise<{
    gap: KnowledgeGap;
  }>;
}

export async function adminResolveKnowledgeGap(
  gapId: number,
  payload: {
    doc_name: string;
    category: string;
    content: string;
    mode: "append" | "overwrite";
    auto_reindex: boolean;
    chunk_size?: number;
    chunk_overlap?: number;
  }
) {
  return req(`/api/admin/knowledge-gaps/${gapId}/resolve`, {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<{
    gap: KnowledgeGap;
    saved_doc: string;
    chunks_indexed: number | null;
  }>;
}

export async function adminListTrainingExamples(filters?: {
  correction_type?: string;
  user_role?: string;
  limit?: number;
  offset?: number;
}) {
  const params = new URLSearchParams();
  if (filters?.correction_type)
    params.set("correction_type", filters.correction_type);
  if (filters?.user_role) params.set("user_role", filters.user_role);
  if (typeof filters?.limit === "number")
    params.set("limit", String(filters.limit));
  if (typeof filters?.offset === "number")
    params.set("offset", String(filters.offset));
  const qs = params.toString();
  return req(`/api/admin/training-examples${qs ? `?${qs}` : ""}`) as Promise<{
    examples: TrainingExample[];
  }>;
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
    `/api/admin/training-quality/groups?limit_per_group=${limitPerGroup}`
  ) as Promise<TrainingQualityGroups>;
}

export type ProductionPromptSummary = {
  fingerprint: string;
  base_prompt_template_hash: string;
  active_overrides: Array<{
    id: number;
    error_type: string;
    one_line_preview: string;
    affected_example_count: number;
  }>;
  active_override_ids: number[];
};

export type TrainingQualitySummary = {
  total_signals: number;
  edited: number;
  rejected: number;
  notes_only: number;
  groups_count: number;
  generated_at: string | null;
  active_prompt_overrides: number;
  max_active_prompt_overrides: number;
  production_prompt?: ProductionPromptSummary;
};

export async function adminGetTrainingQualitySummary() {
  return req(
    "/api/admin/training-quality/summary"
  ) as Promise<TrainingQualitySummary>;
}

export type SystemPromptHeadInfo = {
  builtin_default: string;
  override_active: boolean;
  effective: string;
  char_count: number;
};

export async function adminGetTrainingQualitySystemPromptHead() {
  return req(
    "/api/admin/training-quality/system-prompt-head"
  ) as Promise<SystemPromptHeadInfo>;
}

export async function adminPutTrainingQualitySystemPromptHead(
  overrideText: string
) {
  return req("/api/admin/training-quality/system-prompt-head", {
    method: "PUT",
    body: JSON.stringify({ override_text: overrideText }),
  }) as Promise<{ ok: boolean; using_builtin: boolean }>;
}

export type QuestionBankRow = {
  training_example_id: number;
  preview: string;
  normalized_hash_short: string;
  last_event_at: string | null;
  in_live_prompt: boolean;
  active_override_ids: number[];
  suggestion_affected_events: number;
  ever_override_applied: boolean;
};

export async function adminGetQuestionBank(opts?: {
  limit?: number;
  offset?: number;
  q?: string;
  only_covered?: boolean;
  only_with_override?: boolean;
  only_recent_hours?: number;
}) {
  const params = new URLSearchParams();
  if (typeof opts?.limit === "number") params.set("limit", String(opts.limit));
  if (typeof opts?.offset === "number")
    params.set("offset", String(opts.offset));
  if (opts?.q) params.set("q", opts.q);
  if (opts?.only_covered) params.set("only_covered", "true");
  if (opts?.only_with_override) params.set("only_with_override", "true");
  if (typeof opts?.only_recent_hours === "number")
    params.set("only_recent_hours", String(opts.only_recent_hours));
  const qs = params.toString();
  return req(
    `/api/admin/training-quality/question-bank${qs ? `?${qs}` : ""}`
  ) as Promise<{
    rows: QuestionBankRow[];
    total: number;
    offset: number;
    limit: number;
  }>;
}

export type AnalyzerSupportingExample = {
  id: number;
  missing?: boolean;
  input?: string;
  human_notes?: string;
  reasoning?: string;
  correction_type?: string;
  diff?: Record<string, unknown>;
};

export type AnalyzerGroup = {
  type: string;
  suggested_change: string;
  rationale: string;
  confidence: number;
  affected_ids: number[];
  supporting_examples?: AnalyzerSupportingExample[];
  supporting_examples_omitted_count?: number;
};

export type AnalyzerRagSuggestion = {
  type: string;
  description: string;
  affected_ids: number[];
  supporting_examples?: AnalyzerSupportingExample[];
  supporting_examples_omitted_count?: number;
};

export type HiddenSuggestionReason =
  | "duplicate_rule"
  | "reviewer_discarded"
  | "question_bank_claimed";

export type HiddenSuggestion = {
  kind: string;
  type: string;
  reason: HiddenSuggestionReason;
  suggested_change: string;
  matched_text?: string;
  match_type?: string;
  score?: number | null;
  source?: string | null;
  affected_ids?: number[];
  decision_id?: number | null;
};

export type AnalyzerPayload = {
  cached: boolean;
  cache_key: string;
  generated_at: string | null;
  model: string | null;
  groups: AnalyzerGroup[];
  rag_suggestions: AnalyzerRagSuggestion[];
  duplicate_suggestions_hidden: number;
  discarded_suggestions_hidden: number;
  question_claim_hidden: number;
  hidden_suggestions: HiddenSuggestion[];
};

export async function adminGetTrainingQualityAnalysis(
  llmProfileId?: number | null
) {
  const qs =
    llmProfileId != null && llmProfileId > 0
      ? `?llm_profile_id=${encodeURIComponent(String(llmProfileId))}`
      : "";
  return req(
    `/api/admin/training-quality/analysis${qs}`
  ) as Promise<AnalyzerPayload>;
}

export async function adminRunTrainingQualityAnalysis(
  llmProfileId?: number | null
) {
  const qs =
    llmProfileId != null && llmProfileId > 0
      ? `?llm_profile_id=${encodeURIComponent(String(llmProfileId))}`
      : "";
  return req(`/api/admin/training-quality/analysis/run${qs}`, {
    method: "POST",
  }) as Promise<AnalyzerPayload>;
}

export async function adminDiscardPromptSuggestion(payload: {
  error_type: string;
  suggested_change: string;
  reason?: string;
  affected_example_ids?: number[];
}) {
  return req("/api/admin/training-quality/suggestions/discard", {
    method: "POST",
    body: JSON.stringify({
      error_type: payload.error_type,
      suggested_change: payload.suggested_change,
      reason: payload.reason ?? "",
      affected_example_ids: payload.affected_example_ids ?? [],
    }),
  }) as Promise<{
    decision: {
      id: number;
      error_type: string;
      suggested_change: string;
      decision: string;
      reason: string;
      created_at: string;
    };
  }>;
}

export type ReplaySummary = {
  override_id: number;
  total_original: number;
  passed_original: number;
  total_paraphrases: number;
  passed_paraphrases: number;
  examples_logged: number;
  items: Array<{
    input_text: string;
    is_paraphrase: boolean;
    seed_example_id: number | null;
    actual_output: Record<string, unknown>;
    expected_output: Record<string, unknown>;
    matches_expected: boolean;
    mismatch_fields: string[];
    training_example_id: number | null;
  }>;
};

export type PromptOverrideReplaySnapshot = {
  total_original?: number;
  passed_original?: number;
  total_paraphrases?: number;
  passed_paraphrases?: number;
  examples_logged?: number;
  ran_at?: string;
};

export type PromptOverride = {
  id: number;
  error_type: string;
  suggested_change: string;
  approved_change: string;
  rationale: string;
  status: "pending" | "active" | "rejected" | "superseded";
  affected_example_ids: number[];
  created_by_user_id: number | null;
  created_at: string;
  activated_at: string | null;
  deactivated_at: string | null;
  replay_summary: PromptOverrideReplaySnapshot;
  supporting_examples?: AnalyzerSupportingExample[];
  supporting_examples_omitted_count?: number;
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
  rationale?: string;
  affected_example_ids: number[];
  confidence?: number;
  manually_edited?: boolean;
  force?: boolean;
}) {
  return req("/api/admin/training-quality/overrides/apply", {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<{
    override: PromptOverride;
  }>;
}

export async function adminReplayPromptOverride(
  overrideId: number,
  opts: {
    maxInputs?: number;
    paraphrasesPerInput?: number;
    llmProfileId?: number | null;
  } = {}
) {
  return req(`/api/admin/training-quality/overrides/${overrideId}/replay`, {
    method: "POST",
    body: JSON.stringify({
      max_inputs: opts.maxInputs ?? 6,
      paraphrases_per_input: opts.paraphrasesPerInput ?? 3,
      llm_profile_id: opts.llmProfileId ?? null,
    }),
  }) as Promise<{ summary: ReplaySummary }>;
}

export async function adminRollbackPromptOverride(overrideId: number) {
  return req(`/api/admin/training-quality/overrides/${overrideId}/rollback`, {
    method: "POST",
  }) as Promise<{ override: PromptOverride }>;
}

export async function adminConsolidatePromptOverrides(opts?: {
  force?: boolean;
  llmProfileId?: number | null;
}) {
  return req("/api/admin/training-quality/overrides/consolidate", {
    method: "POST",
    body: JSON.stringify({
      force: opts?.force ?? false,
      llm_profile_id: opts?.llmProfileId ?? null,
    }),
  }) as Promise<{
    override: PromptOverride;
    superseded_ids: number[];
    model: string | null;
  }>;
}

export type LlmModelProfile = {
  id: number;
  name: string;
  provider: string;
  base_url: string;
  default_model: string;
  env_alias: string | null;
  disabled: number;
  created_at: string;
  updated_at: string;
  has_api_key: boolean;
};

export async function adminListLlmProfiles(includeDisabled = false) {
  const q = includeDisabled ? "?include_disabled=1" : "";
  return req(`/api/admin/llm/profiles${q}`) as Promise<{
    profiles: LlmModelProfile[];
  }>;
}

export async function adminCreateLlmProfile(payload: {
  name: string;
  base_url: string;
  default_model: string;
  provider?: string;
  api_key?: string;
  env_alias?: string;
}) {
  return req("/api/admin/llm/profiles", {
    method: "POST",
    body: JSON.stringify(payload),
  }) as Promise<{ profile: LlmModelProfile }>;
}

export async function adminPatchLlmProfile(
  id: number,
  payload: {
    name?: string;
    base_url?: string;
    default_model?: string;
    disabled?: boolean;
    api_key?: string;
    env_alias?: string;
    clear_env_alias?: boolean;
  }
) {
  return req(`/api/admin/llm/profiles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  }) as Promise<{ profile: LlmModelProfile }>;
}

export async function adminDeleteLlmProfile(id: number) {
  return req(`/api/admin/llm/profiles/${id}`, { method: "DELETE" }) as Promise<{
    ok: boolean;
  }>;
}

export async function adminGetLlmTaskDefaults() {
  return req("/api/admin/llm/task-defaults") as Promise<{
    defaults: Record<string, number | null>;
  }>;
}

export async function adminPutLlmTaskDefaults(
  defaults: Record<string, number | null>
) {
  return req("/api/admin/llm/task-defaults", {
    method: "PUT",
    body: JSON.stringify({ defaults }),
  }) as Promise<{ defaults: Record<string, number | null> }>;
}

export type LlmProfileProbeStep = {
  id: string;
  ok: boolean;
  ms: number;
  detail: string;
  extra?: Record<string, unknown>;
};

export type LlmProfileProbeQuickResponse = {
  ok: boolean;
  mode?: "quick";
  snippet: string;
  base_url: string;
  model: string;
};

export type LlmProfileProbeFullResponse = {
  ok: boolean;
  mode: "full";
  profile_id: number;
  base_url: string;
  model: string;
  steps: LlmProfileProbeStep[];
  summary: string;
  snippet: string;
  embed_model: string;
};

export async function adminProbeLlmProfile(
  id: number,
  opts?: { mode?: "quick" | "full" }
) {
  const mode = opts?.mode ?? "quick";
  return req(`/api/admin/llm/profiles/${id}/probe`, {
    method: "POST",
    body: JSON.stringify({ mode }),
  }) as Promise<LlmProfileProbeQuickResponse | LlmProfileProbeFullResponse>;
}

export function isLlmProfileProbeFull(r: unknown): r is LlmProfileProbeFullResponse {
  if (typeof r !== "object" || r === null) return false;
  const o = r as Record<string, unknown>;
  return (
    Array.isArray(o.steps) &&
    o.steps.length > 0 &&
    typeof o.summary === "string" &&
    typeof o.base_url === "string"
  );
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

export type AdminBulkTrainingReviewResult = {
  ok: boolean;
  dry_run: boolean;
  ids_requested: number;
  updated: number;
  would_update?: number;
  missing_ids: number[];
};

export async function adminBulkTrainingExamplesReview(
  payload: {
    ids: number[];
    human_notes?: string | null;
    reasoning?: string | null;
    correction_type?: "pending" | "approved" | "edited" | "rejected" | null;
  },
  opts: { confirm?: boolean; dryRun?: boolean } = {}
) {
  const params = new URLSearchParams();
  if (opts.dryRun) params.set("dry_run", "true");
  if (opts.confirm) params.set("confirm", "true");
  const qs = params.toString();
  const body: Record<string, unknown> = { ids: payload.ids };
  if (payload.human_notes !== undefined) body.human_notes = payload.human_notes;
  if (payload.reasoning !== undefined) body.reasoning = payload.reasoning;
  if (payload.correction_type !== undefined)
    body.correction_type = payload.correction_type;
  return req(`/api/admin/training-examples/bulk-review${qs ? `?${qs}` : ""}`, {
    method: "POST",
    body: JSON.stringify(body),
  }) as Promise<AdminBulkTrainingReviewResult>;
}

export async function adminGetTrainingV1Manifest() {
  return req("/api/admin/training-examples/v1/manifest") as Promise<
    Record<string, any>
  >;
}

export type TrainingV1ExportFile = {
  name: string;
  path: string;
  size_bytes: number;
  updated_at: string;
};

export async function adminListTrainingV1Exports(limit = 20) {
  return req(
    `/api/admin/training-examples/v1/exports?limit=${encodeURIComponent(String(limit))}`
  ) as Promise<{
    exports: TrainingV1ExportFile[];
    dir: string;
  }>;
}

export async function adminExportTrainingV1Jsonl() {
  const res = await fetch(
    `${API_URL}/api/admin/training-examples/v1/export-jsonl`,
    {
      credentials: "include",
    }
  );
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status}`);
  }
  return res.text();
}

export type AdminTrainingExamplesExportPayload = {
  correction_types: string[];
  ids?: number[];
  id_min?: number | null;
  id_max?: number | null;
  created_after?: string | null;
  created_before?: string | null;
  include_actual_output?: boolean;
};

export async function adminExportTrainingExamplesFiltered(
  payload: AdminTrainingExamplesExportPayload
): Promise<string> {
  const res = await fetch(`${API_URL}/api/admin/training-examples/export`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      correction_types: payload.correction_types,
      ids: payload.ids?.length ? payload.ids : null,
      id_min: payload.id_min ?? null,
      id_max: payload.id_max ?? null,
      created_after: payload.created_after ?? null,
      created_before: payload.created_before ?? null,
      include_actual_output: !!payload.include_actual_output,
    }),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (body?.detail) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      detail = "";
    }
    throw new Error(
      `Request failed: ${res.status}${detail ? ` - ${detail}` : ""}`
    );
  }
  return res.text();
}

export async function adminBuildTrainingV1Files(payload?: {
  test_results_path?: string;
  output_dir?: string;
}) {
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
  return req(
    `/api/admin/tickets/${ticketId}/classification-overrides`
  ) as Promise<{
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

export type RagEvalResultRow = {
  id: string;
  category: string;
  message: string;
  expected: Record<string, unknown>;
  actual: Record<string, unknown>;
  pass: boolean;
  failures: string[];
  rate_limit_retries_used: number;
  api_ok: boolean;
  failure_types: string[];
  processed_index: number;
};

export type RagEvalReport = {
  summary: Record<string, unknown>;
  lists: Record<string, unknown>;
  diff: {
    improved: string[];
    regressed: string[];
    still_failed: string[];
  } | null;
  results: RagEvalResultRow[];
};

export type RagEvalJob = {
  id: string;
  status: "queued" | "running" | "completed" | "failed";
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: { done: number; total: number };
  results: RagEvalResultRow[];
  report: RagEvalReport | null;
  summary: Record<string, unknown> | null;
  error: string | null;
  gate_ok: boolean | null;
  gate_message: string | null;
};

export async function adminStartRagEvalJob(form: FormData) {
  const res = await fetch(`${API_URL}/api/admin/rag-eval/jobs`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") {
        detail = body.detail;
      } else if (body?.detail) {
        detail = JSON.stringify(body.detail);
      }
    } catch {
      detail = "";
    }
    throw new Error(
      `Request failed: ${res.status}${detail ? ` - ${detail}` : ""}`
    );
  }
  return res.json() as Promise<{ job_id: string }>;
}

export async function adminGetRagEvalJob(jobId: string) {
  return req(
    `/api/admin/rag-eval/jobs/${encodeURIComponent(jobId)}`
  ) as Promise<{ job: RagEvalJob }>;
}
