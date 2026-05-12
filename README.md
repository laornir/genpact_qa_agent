# University QA Agent

A natural-language question-answering service that translates plain-English questions about a university into SQL queries and returns human-readable answers.

---

## How to Run / Debug

### 1. Create the `.env` file

Copy the template and fill in the two required API keys:

```bash
cp .env.example .env
```

Then open `.env` and set:

| Variable | Where to get it |
|---|---|
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) → API Keys |
| `LANGCHAIN_API_KEY` | [smith.langchain.com](https://smith.langchain.com/) → Settings → API Keys (optional — only needed if `LANGCHAIN_TRACING_V2=true`) |

All other values in `.env` work out of the box for local development (Postgres runs in Docker with the default credentials).

### 2. Start the server

Open the project in VS Code and press **F5** (or Run → Start Debugging → *Debug Server*).

The launch configuration (`.vscode/launch.json`) does two things automatically:

1. Runs `make run-db` as a pre-launch task — this starts the Postgres container via Docker Compose and waits until the database is accepting connections.
2. Launches `uvicorn api.main:app` under the VS Code debugger on `http://localhost:8000`.

Once the server is up:

- **Swagger UI** — `http://localhost:8000/docs` (interactive — try requests in the browser)
- **Health check** — `http://localhost:8000/health`

> **Note:** `--reload` is intentionally absent from the debug configuration. Uvicorn's file-watcher mode forks a child process that the debugger cannot attach to, so breakpoints stop working. Use F5 restart after code changes instead.

---

## Design Decisions

### 2.1 Database-Agnostic Design

The database layer is isolated behind a single abstract interface — `DatabaseConnector` (`db/base.py`) — that declares three async methods: `execute_query`, `fetch_schema`, and `healthcheck`. Concrete adapters (`db/postgres.py` for production, `db/sqlite.py` for tests) implement this interface without the rest of the codebase knowing which backend is active.

Decoupling happens at three levels:

| Level | Mechanism |
|---|---|
| **Schema** | `db/schema_loader.py` calls `connector.fetch_schema()` and converts the raw column records into a compact prompt string (`table: col, fk_col→ref_table.id, …`). Nodes receive only this string — they never see raw DDL or DB-specific types. |
| **SQL generation** | Driver-specific few-shot examples live in `agent/prompts/sql_examples/` (`postgres_examples.sql`, `sqlite_examples.sql`, …). The active file is selected at startup by `DB_DRIVER` so the LLM sees idiomatic SQL for the actual backend. |
| **Connector selection** | `db/factory.py` reads `DB_DRIVER` and instantiates the correct connector. The API layer, graph, and all nodes depend only on `DatabaseConnector`; swapping backends requires no code changes. |

Tests always run with `DB_DRIVER=sqlite` against an in-memory database, while production uses Postgres — with no test-specific branches anywhere in application code.

---

### 2.2 Agent Nodes and Their Roles

The agent is a [LangGraph](https://github.com/langchain-ai/langgraph) `StateGraph` with five nodes. Each node is a pure async function that reads from `AgentState` and writes back to it.

| Node | Role |
|---|---|
| **`question_analyzer`** | Classifies the question as `answerable`, `ambiguous`, or `out_of_scope`. On ambiguous questions it asks a clarification and halts; on continuation turns it first merges the user's new input with the accumulated intent before re-classifying. |
| **`sql_generator`** | Generates a raw SQL SELECT query from the resolved intent. On retry turns the previous failed SQL and the database error are appended to the prompt so the LLM can self-correct. |
| **`sql_validator`** | Checks the generated SQL with a regex-based guard chain (must start with `SELECT`/`WITH`; no stacked statements; no DML/DDL keywords; no system-schema access). Runs entirely in-process — no LLM call. |
| **`sql_executor`** | Runs the validated SQL via the connector and captures the result rows (capped at `DB_RESULTS_ROW_LIMIT`). On a DB error it triggers a retry by routing back to `sql_generator`. |
| **`answer_formatter`** | Summarises the raw query results into a single, readable natural-language answer. |

**Prompt construction**

Each LLM-backed node has a dedicated prompt builder in `agent/prompts/`:

- `question_analyzer` uses two prompts: a **merger prompt** (plain-text system + human, called only on clarification continuations) and a **classifier prompt** (system embeds the schema; human carries the accumulated intent; the LLM must return strict JSON).
- `sql_generator` uses a **system prompt** that embeds the full schema context and the driver-specific few-shot examples, plus a human message that includes the conversation history, the resolved intent, and — on retries — the previous failed attempt.
- `answer_formatter` receives the question and raw DB rows and returns a prose summary.

**System prompt caching**

The schema context is loaded once at FastAPI startup (`lifespan`) and stored in `app.state.schema_context`; a background task refreshes it every 5 minutes. Because the system prompt (which embeds the schema) is identical across all requests that arrive between refreshes, it is a stable prefix and is cached on the server-side, which avoids re-processing repeated token prefixes and reduces both latency and cost.

---

### 2.3 Graph Flow and State

```
question_analyzer
    ├─ answerable      → sql_generator → sql_validator
    │                                        ├─ valid   → sql_executor
    │                                        │               ├─ success → answer_formatter → END
    │                                        │               └─ db error → sql_generator (retry)
    │                                        └─ invalid → END (error)
    ├─ asking_clarification → END  (waits for next HTTP turn)
    └─ error (out_of_scope / limit reached) → END
```

All nodes share a single `AgentState` TypedDict. Fields are grouped into three concerns:

- **Core** — `question`, `schema_context`, `sql`, `sql_error`, `retry_count`, `db_results`, `answer`, `status`
- **Multi-turn** — `conversation_history`, `accumulated_intent`, `last_clarification`, `ambiguity_count`
- **Tracing** — `trace_id`, `session_id`, `tracer`

**Query disambiguation loop**

When a question is ambiguous the agent replies with a clarification question and the HTTP call returns with `status: "asking_clarification"`. The session's context is persisted in an in-memory `SessionStore` (`api/session_store.py`) as a `ConversationHistory` record containing `last_status`, `last_clarification_question`, `accumulated_intent`, and `ambiguity_count`.

On the next HTTP call the API layer checks `history.last_status == "asking_clarification"` to detect a continuation. If true, it carries `last_clarification`, `accumulated_intent`, and `ambiguity_count` forward into the new `AgentState`; otherwise those fields are reset to `None`/`0` (fresh question). Inside `question_analyzer` the non-None `last_clarification` triggers the merger prompt, which combines the old accumulated intent with the user's new answer into a single coherent description before the classifier runs. This loop repeats up to `MAX_CLARIFICATION_ROUNDS` (default: 3); after that the agent returns an error asking the user to rephrase from scratch.

**Why `SessionStore` instead of LangGraph's built-in checkpointing?**

LangGraph ships `MemorySaver` / `AsyncPostgresSaver` checkpointers that persist the full `AgentState` across runs. They are the right tool when a graph run is *interrupted mid-execution* and must be resumed from the same node. That is not the pattern here: when the agent asks a clarification question it completes the graph run normally and returns a full HTTP response. The next call starts a brand-new graph run with the clarification context injected up front — there is no paused run to resume. Beyond the conceptual mismatch, `AgentState` contains non-serializable objects (`Tracer`, `llm`, `connector`) that a checkpointer could not store without custom wrappers. `ConversationHistory` is a minimal four-field dataclass that captures exactly what the API layer needs between turns and nothing more.

---

### 2.4 Logging and Tracing

Two complementary observability layers are active simultaneously and linked by a shared `trace_id` (a UUID generated per HTTP request):

**Application logs** — every node emits structured JSON lines via `Tracer.log()` (`agent/tracing.py`). Each line contains `ts`, `trace_id`, `session_id`, `node`, `event` (`start`/`end`/`error`/`retry`/`clarification_requested`) and relevant context fields (`sql`, `retry_count`, `row_count`, `status`, etc.). Lines go to stdout as plain JSON, making them easy to ship to any log aggregator.

```json
{"ts": "2026-05-12T12:44:06.512604+00:00", "trace_id": "e8f07ff1-…", "session_id": "…", "node": "question_analyzer", "event": "end", "status": "generating"}
{"ts": "2026-05-12T12:44:08.788761+00:00", "trace_id": "e8f07ff1-…", "session_id": "…", "node": "sql_generator",     "event": "end", "sql": "SELECT …", "retry_count": 0}
```

**LangSmith** — when `LANGCHAIN_TRACING_V2=true` every LLM call is captured automatically with the full prompt, completion, token counts, and latency. Each call is tagged with `trace_id` via `config={"metadata": {"trace_id": …}}` so LangSmith traces and application log lines can be correlated.

---

### 2.5 Tests

The test suite has three layers, run with `make test` (`DB_DRIVER=sqlite pytest tests/ -v`):

**Unit tests** (`tests/test_agent/`, `tests/test_db/`)

Each node, prompt builder, and DB adapter is tested in isolation with mocked LLM dependencies:

- `test_question_analyzer` — fresh question vs. clarification continuation; merger prompt skipped on fresh turns; ambiguity counter increments and resets; out-of-scope routing.
- `test_sql_generator` — first-attempt prompt vs. retry prompt (error message appended); conversation history formatting.
- `test_sql_validator` — 18 cases covering the four guard layers: SELECT/WITH whitelist, stacked statements, DML/DDL keywords, and system-schema names.
- `test_sql_executor` — success path, DB error triggers retry routing, row-limit cap.
- `test_tracing` — `Tracer.log()` emits correct JSON fields; `NodeEvent` values serialise as strings.
- `test_db/` — `fetch_schema` returns correct FK notation; `execute_query` returns row dicts; `healthcheck` passes on a live connection.

**End-to-end tests** (`tests/test_e2e/`)

Tests spin up a real FastAPI app backed by an in-memory SQLite database seeded with the full university schema and sample data. The LLM is replaced with a `MagicMock` whose `invoke.side_effect` is set per test to return pre-baked `AIMessage` responses. HTTP calls go through `httpx.AsyncClient` with `ASGITransport` — no network, no real server port.

Four scenarios are covered:

| File | What is tested |
|---|---|
| `test_happy_path.py` | HTTP 200, `status="done"`, non-empty answer, `session_id` echoed, `trace_id` present, `/health` returns `db_ok=true` |
| `test_clarification.py` | Ambiguous question returns `asking_clarification`; follow-up turn resolves to `done`; `answer` field contains the clarification question; 4-turn limit returns `error` |
| `test_retry.py` | DB error on first SQL attempt triggers a retry that succeeds; exhausting all retries returns `error` |
| `test_out_of_scope.py` | Out-of-scope classification returns `error`; LLM called exactly once (classifier only); `answer` is non-empty |

---

## Traces

The `traces/` directory contains four example interactions executed against the live server with the sample seed data. Each trace includes the user query, the system's response, a link to the LangSmith trace, and the application log showing full node-level traceability.

### Happy Path — `traces/happy path.md`

> *"List students and their average grades in Fall 2024 semester"*

A clear, answerable question. The classifier routes directly to SQL generation, the executor returns 3 rows, and the formatter produces a ranked list. Full pipeline in ~7 seconds.

[LangSmith trace](https://smith.langchain.com/public/afcf1d2c-d156-4c64-8325-15f48a2413ba/r)

---

### Multi-Turn Clarification — `traces/simple query refining.md`

> Turn 1: *"List the courses in the university"*  
> Turn 2: *"Courses for Spring semester of 2025 please"*

The classifier judges the first question ambiguous (no semester specified) and asks for clarification. On the second turn the merger prompt combines the two turns into a resolved intent, the classifier approves it, and the SQL generator produces a query filtered to Spring 2025.

[LangSmith trace (turn 1)](https://smith.langchain.com/public/a2b48741-6e26-4298-8d7a-df31520f8232/r) · [LangSmith trace (turn 2)](https://smith.langchain.com/public/96266b20-b607-4955-9440-986510929d46/r)

---

### Out-of-Scope — `traces/general unasnwerable.md`

> *"What is the capital of France?"*

The classifier immediately returns `out_of_scope`. The graph exits after a single LLM call — no SQL is generated or executed.

[LangSmith trace](https://smith.langchain.com/public/7c236a7f-efbd-4081-bac2-4b2743ca65c4/r)

---

### Write-Attempt Blocked — `traces/update score.md`

> *"Update the score of Eve Adams in Algorithms course of semester Spring 2025 to 100"*

The question is classified as answerable but the LLM, instructed to emit only SELECT statements, wraps its refusal in a non-SQL response. While there is a dedicated guardrail to prevent malitious SQL queries, this request is blocked by the sql_generator, following the instruction to generate only SELECT queries.

[LangSmith trace](https://smith.langchain.com/public/6883e5e8-57b6-4102-b901-06b42cf3fb3a/r)

---

## Future Thoughts

This is a demo application. It proves the concept and covers the core happy path, clarification loop, and safety guardrails, but there are many production-readiness improvements worth exploring:

- **Distributed session store** — session context is currently held in a Python dict in the server process. This means sessions are lost on restart and clustering is impossible. Replacing `SessionStore` with Redis would give persistence across restarts, support horizontal scaling behind a load balancer, and allow TTL-based session expiry with no extra code. In addition, the surrent implementation does not remove sessions from memory. using Redis, the session store will be configured to evict stale sessions (TTL, usually 30 minutes).

- **Authentication and row-level authorization** — the current system runs every query with full read access to the database. In a real deployment, queries should be scoped to the authenticated user: a student should only be able to query their own grades and enrollments, a teacher should see only the courses they teach, and an admin should have unrestricted (read) access.
