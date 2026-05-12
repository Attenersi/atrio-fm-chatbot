# FM Chatbot

Taal: [English](README.md) | **Nederlands**

FM Chatbot is een AI-assistent voor Facility Management-teams. De app helpt gebruikers snel en consistent antwoord te krijgen op basis van interne gebouw- en operationele documentatie, met koppeling naar ticketprocessen en review.

Het platform combineert een Next.js-frontend, FastAPI-backend, RAG-retrieval over FM-documenten en admin-kwaliteitstools, zodat teams antwoorden continu kunnen verbeteren in plaats van statisch te houden.

## Voor wie is dit bedoeld

- FM-operatieteams die dagelijkse gebouwvragen afhandelen
- Helpdesk- en supportmedewerkers die verzoeken triëren
- Admins en domeinexperts die documentatie, kwaliteit en guardrails beheren

## Voordelen

- Snellere eerste reactie op veelvoorkomende FM-vragen
- Consistentere antwoorden, gebaseerd op eigen documentatie
- Minder repetitieve tickets door betere self-service
- Meer operationeel inzicht via logs, reviews en kwaliteitsworkflows

## Kernfunctionaliteiten

- Gegronde Q&A over FM-documenten met retrieval-augmented generation (RAG)
- Guardrails tegen prompt-injection en gevoelige outputpatronen
- Ticketgerichte workflow (chatinteracties kunnen supporttickets openen en volgen)
- Adminconsole voor documenten, gebruikers, kennislacunes, trainingsreview en kwaliteitscontrole
- LLM-profielbeheer voor provider/model-standaarden en diagnostiek

## Documentatie

**Canonieke index** (alle gidsen, technische docs, validatie en governance; voornamelijk EN): [`docs/documentation_map.md`](docs/documentation_map.md)
**Volledige request flow (diagrammen, EN):** [`docs/architecture.md`](docs/architecture.md)

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
- `/admin` - documenten, gebruikers, kennislacunes, trainingsreview
- `/admin/training-quality` - evaluatieruns, analyzer-suggesties, prompt-overrides
- `/admin/llm` - LLM-profielen en taakstandaarden

## Platformcomponenten

- Next.js frontend (`frontend/`)
- FastAPI backend (`backend/`)
- SQLite voor operationele data (gebruikers, sessies, tickets, lacunes, trainingsregels)
- Chroma vectorindex voor retrieval
- OpenAI-compatibele LLM-providerintegratie

## Kwaliteit en testen

Voer de RAG-evaluatiesuite uit:

```bash
docker compose exec backend python -u test_rag.py --cases-file atrio_test_cases.json --output test_results_full.json
```

Interpreteer:

- `pass_rate` (alle cases)
- `api_ok_pass_rate` (logica wanneer API-calls slagen)

Zie [`backend/test_runbook.md`](backend/test_runbook.md) voor troubleshooting.
