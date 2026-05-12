# FM Chatbot

Taal: [English](README.md) | **Nederlands**

FM Chatbot is een Facility Management-assistentplatform met:

- Next.js frontend (`frontend/`)
- FastAPI backend (`backend/`)
- SQLite voor operationele data (gebruikers, sessies, tickets, lacunes, trainingsregels)
- Chroma vectorindex voor retrieval (RAG)
- OpenAI-compatibele LLM-providerintegratie

## Wat de app doet

De assistent beantwoordt FM-vragen met RAG, past guardrails toe, kan tickets openen en logt interacties voor review. **Volledige request flow (diagrammen, EN)** staat centraal in [`docs/architecture.md`](docs/architecture.md).

## Documentatie

**Canonieke index** (alle gidsen, technische docs, validatie en governance; voornamelijk EN): [`docs/documentation_map.md`](docs/documentation_map.md)

## Snelle start (alleen Docker)

Aanbevolen op alle platformen: Compose werkt hetzelfde op Windows, macOS en Linux.

Vereisten:

- Docker Desktop (of Docker Engine + Compose plugin)
- geldige `backend/.env` (kopieer vanuit `backend/.env.example` en vul echte secrets in)

Native installatie zonder Docker (venv + npm), met **PowerShell en bash**: [`SECOND_COMPUTER_SETUP.md`](SECOND_COMPUTER_SETUP.md).

### 1) Build en start

```bash
docker compose up --build
```

Open `http://localhost:3000`.

### 2) Ingest FM-documenten (eerste run en na wijzigingen)

```bash
docker compose exec backend python -m app.ingest
```

### 3) Handige operationele commando's

```bash
# services stoppen
docker compose down

# backend logs
docker compose logs -f backend

# frontend logs
docker compose logs -f frontend
```

## Belangrijkste productzones

- `/chat` - gesprekken en automatische ticketaanmaak
- `/dashboard` - ticketlijst, statistieken, filters en statussen
- `/help` - in-app handleiding
- `/admin` - documenten, users, kennislacunes, training review
- `/admin/training-quality` - eval runs, analyzer, prompt overrides
- `/admin/llm` - LLM-profielen en task defaults

## Kwaliteit en testen

Voer de RAG-evaluatiesuite uit:

```bash
docker compose exec backend python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Interpreteer:

- `pass_rate` (alle cases)
- `api_ok_pass_rate` (logica wanneer API-calls slagen)

Zie [`backend/test_runbook.md`](backend/test_runbook.md) voor troubleshooting.
