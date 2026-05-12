# Observability (target story vs today)

This document describes the **observability posture you should plan for** when operating a chatbot that **creates tickets automatically**. It does **not** claim the current codebase implements every item.

## Today (honest baseline)

- Python **logging** is used in places (e.g. `fm.observability`, `fm.training_quality`). There is **no** default **JSON** log format; operators can configure formatters and use the **`request_id`** field on log records (see below).
- **Request correlation:** every HTTP request gets an **`X-Request-ID`** (client-supplied if valid, otherwise generated). It is stored in a **context variable**, echoed on the response, and injected into log records for `fm.observability` and `fm.training_quality` as `%(request_id)s` when your logging format includes it. It is **not** yet threaded into every internal LLM/RAG log line by name (that remains roadmap).
- **Evaluation** pass rates are primarily from **batch** runs (e.g. `test_rag.py`, CI smoke eval)—useful for regression gates, not continuous production SLO monitoring.
- No bundled **metrics** server (Prometheus/OpenTelemetry) or **error tracking** SDK (Sentry, etc.) is part of the default install.

## Target capabilities (roadmap)

### Structured logging

- **JSON logs** (one object per line) from the backend in production, with **severity** and **timestamp** (UTC).
- **Log level** driven by environment (e.g. `LOG_LEVEL=INFO`).
- **Stable field names** for route, status code, duration, `user_id` (hashed or absent if policy forbids), and **ticket_created**.

### Request tracing

- Accept or generate **`X-Request-ID`** (or W3C `traceparent` later); store it in a **context variable** and include it on every log line for that request.
- Propagate the same id through **chat**, **RAG retrieval**, **LLM calls**, and **ticket creation** so incidents can be traced end-to-end.

### Error tracking

- Optional integration with **Sentry** (or similar) for the **FastAPI** process and optionally the **Next.js** frontend, with PII scrubbing and environment tags (`production`, `staging`).

### Metrics and SLOs

Examples to track over time:

- **p50/p95 latency** for `/api/chat` and `/api/chat/stream`.
- **Ticket creation rate** and error rate on ticket insert paths.
- **RAG retrieval** latency and failure rate (empty results vs errors).
- **Eval pass rate** (from scheduled jobs) as a lagging quality indicator—not a substitute for live alerts.

### Alerting

- Alert on **error rate spikes**, **LLM health** degradation, and **sudden ticket volume** anomalies, tuned per organization.

Implementation entry points: [`backend/app/main.py`](../backend/app/main.py) (HTTP middleware), [`backend/app/request_context.py`](../backend/app/request_context.py) (contextvar + log filter).

## Related

- [`ci.md`](ci.md) — CI eval gate.
- [`README_developers.md`](README_developers.md) — running eval locally.
