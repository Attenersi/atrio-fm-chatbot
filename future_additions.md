# Atrio — Database Schema Plan

## MVP Tables (v1.0)

### tickets
Primary table for all maintenance requests created by AI.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | Unique ticket ID |
| ticket_ref | TEXT UNIQUE | Human-readable ref: TKT-0001, TKT-0002... |
| message | TEXT NOT NULL | Original tenant message (verbatim) |
| issue_summary | TEXT | AI-generated summary of the problem |
| response | TEXT | AI response sent back to tenant |
| category | TEXT NOT NULL | HVAC / Electrical / Plumbing / Safety / General |
| priority | TEXT NOT NULL | URGENT / HIGH / NORMAL / LOW |
| department | TEXT | Auto-assigned department based on category |
| status | TEXT DEFAULT 'open' | open / assigned / in_progress / resolved / closed |
| building | TEXT | Building name (for multi-building future) |
| location | TEXT | Room/floor extracted from message (e.g. "Suite 204, Floor 2") |
| reported_by | TEXT | Tenant email or name (if known) |
| assigned_to | TEXT | Technician/team name (set by manager) |
| notification_sent | BOOLEAN DEFAULT false | Whether email notification was sent |
| created_at | DATETIME DEFAULT NOW | When ticket was created |
| updated_at | DATETIME DEFAULT NOW | Last status change |
| resolved_at | DATETIME NULL | When ticket was resolved |

### conversations
Chat history per session. Links to ticket if one was created.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | Message ID |
| session_id | TEXT NOT NULL | UUID grouping messages in one chat session |
| role | TEXT NOT NULL | 'user' or 'assistant' |
| content | TEXT NOT NULL | Message text |
| ticket_id | INTEGER FK NULL | Links to tickets.id if this message created a ticket |
| created_at | DATETIME DEFAULT NOW | Timestamp |

### documents
Tracks what's in the knowledge base (for admin panel).

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | Document ID |
| filename | TEXT NOT NULL | Original filename |
| title | TEXT | Document title extracted from content |
| chunk_count | INTEGER | How many chunks it was split into |
| word_count | INTEGER | Total words |
| ingested_at | DATETIME DEFAULT NOW | When it was added to ChromaDB |
| status | TEXT DEFAULT 'active' | active / archived |

---

## Future Tables (v2.0+)

### resolution_notes
What the FM team did to fix the problem. Powers "learning from resolved tickets."

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | |
| ticket_id | INTEGER FK NOT NULL | Links to tickets.id |
| note | TEXT NOT NULL | What was done: "Replaced VRF filter in unit 204-B" |
| added_by | TEXT | Manager/technician name |
| parts_used | TEXT NULL | "VRF filter model X, condensate pump" |
| cost | DECIMAL NULL | Repair cost if tracked |
| time_spent_minutes | INTEGER NULL | How long the fix took |
| created_at | DATETIME DEFAULT NOW | |

**AI use:** When a similar ticket comes in, retrieve matching resolution_notes by category + location + keyword similarity. Add to LLM context: "Previous similar issue was resolved by [note]."

### classification_overrides
When a manager corrects the AI's classification. Powers "calibration feedback loop."

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | |
| ticket_id | INTEGER FK NOT NULL | Which ticket was corrected |
| field_changed | TEXT NOT NULL | 'category' or 'priority' or 'department' |
| ai_value | TEXT NOT NULL | What AI originally assigned |
| manager_value | TEXT NOT NULL | What manager changed it to |
| changed_by | TEXT | Manager name |
| created_at | DATETIME DEFAULT NOW | |

**AI use:** Aggregate overrides to find patterns: "AI keeps classifying elevator issues as General, manager always changes to Safety → adjust system prompt or add rule."

### recurring_patterns
Auto-detected repeated issues. Powers "pattern detection."

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | |
| pattern_type | TEXT NOT NULL | 'same_location' / 'same_category' / 'same_description' |
| description | TEXT | "HVAC complaints in Suite 305 — 4 tickets in 60 days" |
| ticket_ids | TEXT | JSON array of related ticket IDs: [12, 27, 33, 41] |
| location | TEXT NULL | Room/floor if location-based pattern |
| category | TEXT NULL | Category if category-based pattern |
| occurrences | INTEGER | How many times detected |
| first_seen | DATETIME | First ticket in pattern |
| last_seen | DATETIME | Most recent ticket in pattern |
| flagged | BOOLEAN DEFAULT false | Whether FM manager has been alerted |
| resolved | BOOLEAN DEFAULT false | Whether root cause was addressed |
| created_at | DATETIME DEFAULT NOW | |

**AI use:** Cron job or on-ticket-creation check: "Are there 3+ tickets with same category + location in last 60 days? If yes, create pattern entry and flag in dashboard."

### faq_analytics
Tracks what tenants ask most often. Powers "learning from tenant behavior."

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | |
| question_cluster | TEXT NOT NULL | Normalized topic: "wifi_password", "parking_location", "badge_request" |
| sample_messages | TEXT | JSON array of actual messages in this cluster |
| count | INTEGER DEFAULT 1 | How many times asked |
| avg_confidence | DECIMAL | Average RAG confidence score for answers |
| answered_from_kb | BOOLEAN | Whether knowledge base had a good answer |
| first_asked | DATETIME | |
| last_asked | DATETIME | |

**AI use:** Monthly report: "Top 10 questions. 3 of them had low confidence answers — consider adding better documentation for these topics."

### clients (multi-tenant)
One row per customer company using Atrio.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | |
| name | TEXT NOT NULL | "VanDalen Facility Services" |
| slug | TEXT UNIQUE | "vandalen" (used in URLs, API keys) |
| buildings | TEXT | JSON array: ["Meridian Business Center", "Park Tower"] |
| categories | TEXT | JSON custom categories: ["HVAC", "Electrical", "Elevator", ...] |
| departments | TEXT | JSON mapping: {"HVAC": "Climate Team", ...} |
| branding | TEXT | JSON: {"logo_url": "...", "primary_color": "#1E2B4F", "welcome_message": "..."} |
| notification_email | TEXT | Where urgent tickets go |
| webhook_url | TEXT NULL | Slack/Teams webhook |
| api_key | TEXT NULL | Client's own NVIDIA API key (BYOK) |
| chromadb_collection | TEXT | Separate knowledge base collection name |
| plan | TEXT DEFAULT 'free' | free / starter / pro / enterprise |
| ticket_limit | INTEGER DEFAULT 100 | Monthly ticket limit per plan |
| tickets_this_month | INTEGER DEFAULT 0 | Counter, reset monthly |
| created_at | DATETIME DEFAULT NOW | |

### users
FM managers, technicians, admins who log into dashboard.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | |
| client_id | INTEGER FK NOT NULL | Links to clients.id |
| email | TEXT UNIQUE NOT NULL | Login email |
| name | TEXT NOT NULL | Display name |
| password_hash | TEXT NOT NULL | bcrypt hashed |
| role | TEXT DEFAULT 'viewer' | admin / manager / technician / viewer |
| notify_urgent | BOOLEAN DEFAULT false | Receive urgent ticket emails |
| created_at | DATETIME DEFAULT NOW | |
| last_login | DATETIME NULL | |

### tenant_satisfaction
Post-resolution feedback. Powers "satisfaction tracking."

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK AUTO | |
| ticket_id | INTEGER FK NOT NULL | |
| rating | INTEGER NOT NULL | 1-5 stars |
| comment | TEXT NULL | Optional feedback text |
| created_at | DATETIME DEFAULT NOW | |

---

## Implementation Order

**MVP (now):**
tickets + conversations + documents
→ This is your working product.

**v1.5 (after first tests):**
resolution_notes + classification_overrides
→ Start collecting learning data from day 1.

**v2.0 (first clients):**
clients + users + recurring_patterns + faq_analytics
→ Multi-tenant, login, pattern detection.

**v3.0 (growth):**
tenant_satisfaction + BYOK + advanced analytics
→ Premium features for paying clients.

---

## Key Relationships

```
clients (1) ──→ (many) users
clients (1) ──→ (many) tickets
clients (1) ──→ (many) documents

tickets (1) ──→ (many) conversations
tickets (1) ──→ (many) resolution_notes
tickets (1) ──→ (1) classification_overrides
tickets (1) ──→ (1) tenant_satisfaction

recurring_patterns ──→ references multiple tickets (JSON array)
faq_analytics ──→ aggregated from conversations
```