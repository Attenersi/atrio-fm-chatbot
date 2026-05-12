# Features

Canonical feature inventory for FM Chatbot. Keep this file as the source of truth for shipped user-facing capabilities; keep `README.md` concise and link here for exhaustive detail.

## Product purpose

FM Chatbot helps Facility Management teams answer building and operations questions faster, route actionable incidents into ticket workflows, and continuously improve quality through admin review tooling.

## All authenticated users

- Sign in with username/password and keep an authenticated session
- Register a new account
- Automatic role-based redirect after login (`admin` -> admin console, `user` -> chat)
- Logout from the app shell
- Switch interface language (English / Dutch)
- Switch visual theme (light / dark)
- Use responsive navigation including mobile sidebar behavior

## End-user capabilities

### Chat and ticketing (`/chat`)

- Ask FM questions in a conversational interface
- Stream assistant responses in real time
- See response metadata (category, priority, query type)
- See grounding sources used by the response
- Receive ticket creation confirmation (`ticket_id` or `ticket_ids` for multi-issue prompts)
- Use fallback action **Create ticket anyway** for informational outcomes
- Load prior chat history from server-side storage
- Start a new chat thread

### Dashboard and ticket operations (`/dashboard`)

- View high-level ticket stats (total, urgent)
- View category and trend charts
- Filter by category, priority, and status
- Sort by id, created time, priority, or status
- Page through ticket results
- Update ticket status (`Open`, `In Progress`, `Resolved`)
- Export current ticket view to CSV
- Open ticket detail drawer with message, summary, response, and metadata

### Help (`/help`)

- Use tabbed in-app operational guidance
- Deep-link to specific help sections via URL hash
- Follow workflow guidance for chat, dashboard, and admin-adjacent tasks

## Admin capabilities

Admin users can access all user capabilities plus the administration console.

### Admin console navigation (`/admin`)

- Access tabs for Tickets, Knowledge Gaps, Documents, Users, RAG Eval, Training, Training Quality, and LLM profiles

### Tickets operations (`/admin/tickets`)

- Load ticket operational history by ID
- Add resolution notes (free text, parts used, cost, time spent)
- Add classification overrides (`category`, `priority`, `department`)
- Review note history and override history
- Sync override effects into training examples

### Knowledge gaps (`/admin/knowledge/gaps`, `/admin/gaps/[id]`)

- List knowledge gaps and filter by status (`new`, `reviewed`, `resolved`)
- Inspect gap reason/context and related metadata
- Resolve a gap by writing/merging knowledge into docs
- Choose category (preset or custom)
- Save in append or overwrite mode
- Trigger optional auto-reindex as part of resolution

### Documents and retrieval settings (`/admin/knowledge/documents`)

- List and open existing docs
- Edit and save docs
- Create new docs
- Delete docs
- Upload supported files (`.txt`, `.md`, `.csv`, `.pdf`, `.docx`)
- Configure upload behavior (overwrite converted target, auto-reindex)
- Trigger manual reindex
- Configure ingest chunk size and overlap
- Configure/clear RAG `top_k` override
- Inspect ingest pre-chunk runtime options

### User management (`/admin/users`)

- List users
- Update user role (`user` / `admin`)
- Activate/deactivate users
- Update optional email metadata
- Operate with active-admin guardrails

### RAG evaluation (`/admin/rag-eval`)

- Start asynchronous eval jobs
- Run builtin or uploaded suite (JSON/CSV)
- Optionally compare against prior report JSON
- Configure retries, waits, timeout, and gate thresholds
- Monitor job status and progress
- Inspect per-case pass/fail rows and failure reasons
- Download final JSON report

### Training review (`/admin/training`)

- Browse and filter training examples
- Search by ID and text
- Review and label examples (`pending`, `approved`, `edited`, `rejected`)
- Edit structured expected output fields
- Add human notes and reasoning
- Use keyboard shortcuts for rapid triage
- Bulk update examples by ID (preview/apply)
- Export filtered training data and v1 train set
- Save snapshot files and inspect export history
- View review stats and manifest metadata

### Training quality (`/admin/training-quality`)

- View and edit system prompt head override
- Save, reset, and clear override state
- Keep effective prompt behavior aligned with quality workflows

### LLM profile management (`/admin/llm`)

- Create provider/model profiles
- Set API key inline or via environment alias
- Map default profile per task (`chat`, `analyzer`, `embed`, etc.)
- Enable/disable or remove profiles
- Run quick and full connectivity probes
- Inspect full probe diagnostics (step-by-step checks)

## Notifications and email flows

- New ticket creation emails to admin recipients when SMTP + mail settings are configured
- Batch email for multiple tickets created from one chat turn
- Ticket status-change email to admins and, when available, ticket creator email
- New-ticket notification scope configurable via `MAIL_NOTIFY_NEW_TICKETS` (`all`, `urgent`, `off`)

## Scope notes

- The assistant is intentionally limited to Facility Management scope
- Feature behavior may depend on configured docs quality, reindex state, and deployment environment configuration
