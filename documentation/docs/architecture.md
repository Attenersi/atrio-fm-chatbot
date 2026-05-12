# Architecture and request flow

This is the **canonical** description of how FM Chatbot fits together. Other docs link here instead of duplicating the narrative.

## System context

```mermaid
flowchart TB
  subgraph client["Client"]
    U[User browser]
    FE[Next.js frontend]
  end

  subgraph server["Backend"]
    API[FastAPI app]
    RAG[RAG pipeline]
    CLS[classifier and rules]
  end

  subgraph data["Data and models"]
    SQL[(SQLite)]
    CH[(Chroma)]
    DOC[FM documents]
  end

  subgraph external["External"]
    LLM[OpenAI-compatible LLM API]
  end

  U --> FE
  FE -->|HTTP JSON / SSE| API
  API --> RAG
  RAG --> CH
  RAG --> LLM
  API --> CLS
  CLS --> SQL
  API --> SQL
  DOC -->|ingest embeddings| CH
```

## Chat request flow

Typical path for `/api/chat` or `/api/chat/stream`:

```mermaid
sequenceDiagram
  participant B as Browser
  participant F as Next.js
  participant A as FastAPI
  participant C as Chroma
  participant L as LLM
  participant D as SQLite

  B->>F: User message
  F->>A: POST /api/chat or /api/chat/stream
  A->>C: Retrieve RAG context
  C-->>A: Relevant chunks
  A->>L: Completion (structured output)
  L-->>A: Model response
  A->>A: Parse, normalize, guardrails
  alt Ticket needed
    A->>D: Insert ticket(s), notes, gaps, etc.
  end
  A->>D: Log training / quality rows as configured
  A-->>F: Reply (or streamed tokens)
  F-->>B: UI update
```

## Where to read more

- **HTTP API (live)**: [OpenAPI / interactive docs](#openapi) — run the backend and open `/docs` or `/redoc`.
- **SQLite schema**: [`docs/schema.md`](schema.md) (tables, keys, relationships; code source of truth remains `backend/app/database.py` plus `backend/alembic/versions/*`).
- **Module map**: [`docs/README_developers.md`](README_developers.md) — “Main backend modules” and “Where to change behavior”.

## OpenAPI

FastAPI exposes the generated contract at:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

With Docker Compose (default ports), use the same paths on port **8000** on the host.

Prefer these URLs over static endpoint lists in markdown: the live spec stays accurate as routes change.
