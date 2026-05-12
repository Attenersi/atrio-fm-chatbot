# GDPR-oriented data handling and retention

**Not legal advice.** This document helps **technical and operational teams** describe how this product handles personal data in **Dutch / EU-style deployments**. Your **data controller** (typically the building operator, employer, or customer organization) must align practices with applicable law, contracts, and internal policy. **Processors** may include hosting providers, the LLM API vendor, and email/infrastructure services—each needs appropriate agreements (e.g. DPA, SCCs for third-country transfers).

## Personal data categories in this product

Depending on configuration and usage, the stack may process:

| Area | Examples |
| --- | --- |
| Accounts | `users` (username, password hash, role, active flag, optional `email`, timestamps) |
| Sessions | Session identifiers and expiry (`sessions`), plus browser cookies used for authentication |
| Chat | `chat_threads`, `chat_messages` — **verbatim user messages** and model replies |
| Training capture | `training_examples` — user queries, model outputs, lineage (`user_id`, roles, ticket links, reviewer notes); `training_question_prompt_events` for quality/analysis history |
| Tickets | `tickets` — free-text reports, summaries, responses; `created_by_user_id` links to an account |
| Admin / audit | Prompt override audit, classification overrides, resolution notes—may reference users or free text |

**Fine-tuning exports:** See [`fine_tuning_data.md`](fine_tuning_data.md). Exports can contain the same classes of data as the database; treat them as **highly sensitive** and never use a **production** database snapshot for model-trainer handoff without **pseudonymization** and a clear legal basis.

## Purposes and lawful bases (deployment decisions)

Organizations must map processing to **Article 6** GDPR lawful bases. Illustrative mapping (you must confirm with legal counsel):

- **Service delivery** (responding in chat, creating tickets): typically **contract** or **legitimate interests** of the controller, depending on context.
- **Security, abuse prevention, incident investigation**: often **legitimate interests** or **legal obligation**, depending on sector and policy.
- **Optional model improvement / training-data capture**: often **consent** or **legitimate interests** with a clear **privacy notice** and, where required, **opt-in or opt-out** for retaining queries for training—**do not assume** chat logging for fine-tuning is lawful without an explicit organizational decision.

Subprocessors (LLM inference, hosting) and **third-country transfers** (e.g. inference in the United States) require your own transfer impact assessment, DPAs, and possibly Standard Contractual Clauses.

## Retention

**This open-source product does not enforce a default retention period** for chat, training rows, or tickets. Backups, logs, and exports may retain copies independently of the live database.

**Recommended:** define organizational retention (e.g. delete chat and training data after N months, ticket archive rules, backup rotation) and review periodically.

## Data subject rights — what is supported today vs gaps

| Right | Today | Gaps / notes |
| --- | --- | --- |
| Access | Partial: data lives in SQLite and admin UIs; **no** self-service “download my data” bundle | Full **DSAR JSON export** is a future enhancement |
| Erasure | Admins can call **`POST /api/admin/users/{user_id}/erase-chat-training-data`** (with confirmation) to remove **chat history** and **`training_examples` / related events** for that `user_id` | **Does not** delete the `users` row, **sessions**, or **tickets** by default; tickets may need **manual redaction** or a separate FM/legal process |
| Restriction / portability | No dedicated product workflows | Use DB/export procedures under controller instruction |
| Automated decision-making | Classifier/LLM outputs are assistive; organizational policy defines human review | Document in your DPIA as needed |

## Operational checklist (controller)

- Publish a **privacy notice** (URL) covering chat, tickets, training capture, and subprocessors.
- Maintain **DPAs** and transfer tools with vendors.
- Define **training-data** wording: opt-in, opt-out, or no capture.
- Define **incident response** and a **privacy contact** (see root [`SECURITY.md`](../SECURITY.md) for security reporting; add internal privacy contact separately).

## Explicit non-goals (product)

- Full **self-service** DSAR UI or automated SAR export.
- Default **retention cron** or TTL in the application (organizations may use SQL maintenance, backup policy, or external jobs).
- Automatic **ticket** anonymization (legal/ops tradeoff; not enabled by default).

## Related documentation

- [`fine_tuning_data.md`](fine_tuning_data.md) — training lifecycle and exports
- [`schema.md`](schema.md) — table relationships
- [`documentation_map.md`](documentation_map.md) — index of all guides
