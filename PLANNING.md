# University QA Agent — Planning Document

> This document captures all design decisions made during planning.

---

## Project Overview

A question-answering system over a university database.
Users ask natural language questions and receive accurate answers backed by SQL queries.

**Stack:** Python, FastAPI, PostgreSQL, LangGraph, LangSmith

---

## 1. Project Structure

```
university-qa-agent/
│
├── Makefile
├── docker-compose.yml
├── .env.example
├── .env                              ← gitignored
├── pyproject.toml
├── README.md
├── PLANNING.md
│
├── db/
│   ├── base.py                       ← abstract DatabaseConnector
│   ├── postgres.py                   ← PostgreSQL adapter (asyncpg)
│   ├── sqlite.py                     ← SQLite adapter (tests only)
│   ├── factory.py                    ← reads DB_DRIVER, returns correct impl
│   ├── schema_loader.py              ← introspects DB, builds schema context string
│   └── migrations/
│       ├── 001_initial.sql           ← schema DDL
│       └── 002_seed.sql              ← seed data
│
├── agent/
│   ├── graph.py                      ← LangGraph graph assembly
│   ├── state.py                      ← AgentState TypedDict
│   ├── tracing.py                    ← Tracer class, NodeEvent enum
│   ├── nodes/
│   │   ├── question_analyzer.py
│   │   ├── sql_generator.py
│   │   ├── sql_validator.py
│   │   ├── sql_executor.py
│   │   └── answer_formatter.py
│   └── prompts/
│       ├── question_analyzer.py      ← build_merger_prompt(), build_classifier_prompt()
│       ├── sql_generator.py          ← build_sql_prompt()
│       ├── answer_formatter.py       ← build_answer_prompt()
│       ├── helpers.py                ← format_history(), format_db_results(), truncate_results()
│       └── sql_examples/
│           ├── __init__.py           ← load_few_shot_examples(driver) loader
│           ├── postgres_examples.sql
│           ├── mysql_examples.sql
│           └── sqlite_examples.sql   ← simpler syntax, used in tests
│
├── api/
│   ├── main.py                       ← FastAPI app + lifespan
│   ├── routes.py
│   ├── dependencies.py               ← connector + schema_context injection
│   └── session_store.py              ← in-memory {session_id → ConversationHistory}
│
├── config/
│   └── settings.py                   ← pydantic-settings, reads .env
│
└── tests/
    ├── conftest.py                    ← sqlite_connector, mock_llm, mock_tracer fixtures
    ├── test_db/
    │   ├── conftest.py               ← seeds SQLite before each test
    │   ├── test_schema.py
    │   └── test_queries.py
    ├── test_agent/
    │   ├── conftest.py
    │   ├── test_question_analyzer.py
    │   ├── test_sql_generator.py
    │   ├── test_sql_validator.py
    │   ├── test_sql_executor.py
    │   ├── test_answer_formatter.py
    │   └── test_few_shot_loader.py
    └── test_e2e/
        ├── conftest.py               ← full graph wired with SQLite + mock LLM
        ├── test_happy_path.py
        ├── test_clarification.py
        ├── test_retry.py
        └── test_out_of_scope.py
```

---

## 2. Database Schema

### Entities

```sql
teachers
  id              SERIAL PRIMARY KEY
  name            VARCHAR NOT NULL
  email           VARCHAR UNIQUE NOT NULL

students
  id              SERIAL PRIMARY KEY
  name            VARCHAR NOT NULL
  email           VARCHAR UNIQUE NOT NULL
  enrollment_year INT NOT NULL

courses
  id              SERIAL PRIMARY KEY
  name            VARCHAR NOT NULL
  credits         INT NOT NULL

semesters
  id              SERIAL PRIMARY KEY
  name            VARCHAR NOT NULL        -- e.g. "Fall 2024"
  year            INT NOT NULL
  season          ENUM(spring, summer, fall)

course_offerings
  id              SERIAL PRIMARY KEY
  course_id       → courses.id
  teacher_id      → teachers.id
  semester_id     → semesters.id
  syllabus_url    VARCHAR
  room            VARCHAR
  max_capacity    INT

enrollments
  id              SERIAL PRIMARY KEY
  student_id      → students.id
  offering_id     → course_offerings.id
  grade           NUMERIC(5,2)            -- nullable = not yet graded
  enrolled_at     TIMESTAMP NOT NULL
```

### Key Design Decisions
- No `departments` table — kept intentionally simple
- `course_offerings` separates course definition (static) from a specific taught instance
- `semesters` is a proper entity, not a string field — enables filtering by year/season
- `grade` lives on `enrollments` — it is a property of the relationship, not the student or course
- `syllabus_url` on `course_offerings` — per offering, not per course

---

## 3. DB-Agnostic Connector

### Abstract Interface (`db/base.py`)

```python
class DatabaseConnector(ABC):
    @abstractmethod
    async def execute_query(self, sql: str) -> list[dict]: ...

    @abstractmethod
    async def fetch_schema(self) -> list[dict]: ...
    # returns: [{table, column, type, is_fk, references}, ...]

    @abstractmethod
    async def healthcheck(self) -> bool: ...
```

### Factory (`db/factory.py`)

```python
def get_connector() -> DatabaseConnector:
    match os.getenv("DB_DRIVER", "postgres"):
        case "postgres": return PostgresConnector(settings.postgres_dsn)
        case "mysql":    return MySQLConnector(settings.mysql_dsn)
        case "sqlite":   return SQLiteConnector(settings.sqlite_path)
```

### Schema Context String (produced by `db/schema_loader.py`)

Each concrete adapter implements `fetch_schema()` with its own `information_schema` query.
The loader calls `connector.fetch_schema()` and formats output into a prompt-ready string:

```
teachers: id, name, email
students: id, name, email, enrollment_year
courses: id, name, credits
semesters: id, name, year, season
course_offerings: id, course_id→courses.id, teacher_id→teachers.id,
                  semester_id→semesters.id, syllabus_url, room, max_capacity
enrollments: id, student_id→students.id, offering_id→course_offerings.id,
             grade, enrolled_at
```

Schema is loaded once at FastAPI startup and cached (5 min TTL). Nodes never call the DB directly for schema.

---

## 4. Agent State

```python
class AgentState(TypedDict):
    # core
    question              : str
    schema_context        : str
    sql                   : str | None
    sql_error             : str | None
    retry_count           : int
    db_results            : list[dict] | None
    answer                : str | None
    status                : Literal[
                              "analyzing", "generating", "validating",
                              "executing", "formatting",
                              "asking_clarification", "error", "done"
                            ]
    # multi-turn
    conversation_history  : list[dict]   # [{role, content}, ...] last N turns
    accumulated_intent    : str | None   # grows across clarification turns
    last_clarification    : str | None   # question agent asked last turn
    ambiguity_count       : int          # resets on resolution
    # tracing
    trace_id              : str
    session_id            : str
    tracer                : Tracer
```

---

## 5. Agent Graph

### Node Responsibilities

| Node | LLM? | Responsibility |
|---|---|---|
| `question_analyzer` | ✅ | Merge intent (if resuming), classify ambiguity, route |
| `sql_generator` | ✅ | Generate SQL from accumulated_intent + schema + history |
| `sql_validator` | ❌ | Pure Python guardrail — blocks unsafe SQL |
| `sql_executor` | ❌ | Runs SQL via connector, handles DB errors |
| `answer_formatter` | ✅ | Converts raw DB results to natural language |

### Graph Flow

```
[question_analyzer]
    │
    ├─ out_of_scope ──────────────────────────────→ [terminal: error]
    │
    ├─ ambiguous + under limit ───────────────────→ [terminal: clarification]
    │   (increment ambiguity_count, update accumulated_intent,
    │    set last_clarification)
    │
    ├─ ambiguous + at limit ──────────────────────→ [terminal: error]
    │   "Too many ambiguous questions, please rephrase from scratch."
    │
    └─ answerable ────────────────────────────────→ [sql_generator]
                                                          │
                                                   [sql_validator]
                                                          │
                                              ┌───────────┴──────────┐
                                           invalid                  valid
                                              │                       │
                                       [terminal: error]       [sql_executor]
                                                                      │
                                                         ┌────────────┴───────────┐
                                                      db_error               success
                                                         │                       │
                                                  retry < limit          [answer_formatter]
                                                         │                       │
                                                  [sql_generator]         [terminal: done]
                                                  (with error context)
                                                         │
                                                  retry >= limit
                                                         │
                                                  [terminal: error]
```

### Multi-Turn / Clarification Loop

- `conversation_history`: last N turns (configurable, default 6) injected into `sql_generator` prompt for reference resolution ("that course" → "Algorithms")
- `accumulated_intent`: grows each clarification turn — never reset until resolution
- `ambiguity_count`: increments each clarification round, resets to 0 on resolution
- `last_clarification`: tells `question_analyzer` we are resuming — triggers intent merger before re-classifying

### Session Management (API layer)

```
POST /chat
{
  "session_id": "abc-123",   ← client-generated, stable per conversation
  "question":   "..."
}
```

`session_store.py` holds `{session_id → ConversationHistory}` in memory.
Production replacement: Redis.

Flow per request:
1. Load history from session store
2. Inject into initial AgentState
3. Run graph
4. Append new turn to history, save back

---

## 6. Prompts Design

All prompts are **Python functions** (not string constants) in `agent/prompts/`.
Nodes call `build_*_prompt()` functions — no string building inside nodes.

### `question_analyzer` prompts

**Merger prompt** (only when `last_clarification` is set):
- Input: `accumulated_intent`, `last_clarification`, `current_input`
- Output: updated plain-text description of user intent
- LLM returns plain string, overwrites `accumulated_intent`

**Classifier prompt**:
- Input: `accumulated_intent`, `schema_context`
- Output: strict JSON `{status, clarification_question, reason}`
- `reason` is logged only, never shown to user

### `sql_generator` prompt

- Input: `schema_context`, `few_shot_examples`, `conversation_history`, `accumulated_intent`
- On retry: appends retry block with previous SQL + error message
- Output: raw SQL string, no markdown, no explanation
- Retry block only injected when `retry_count > 0`

### `answer_formatter` prompt

- Input: original `question`, `db_results` (JSON, truncated to configurable row limit)
- Output: natural language answer
- Handles: empty results, single values, lists (prose < 5 items, bullets >= 5)
- Explicitly instructed: do not mention SQL

### Few-Shot Examples (`agent/prompts/sql_examples/`)

```
sql_examples/
  __init__.py              ← load_few_shot_examples(driver: str) -> str
  postgres_examples.sql    ← Postgres dialect
  mysql_examples.sql       ← MySQL dialect
  sqlite_examples.sql      ← SQLite dialect (tests)
```

Loader reads `DB_DRIVER` env var, loads matching file. Raises `ValueError` for unknown drivers.
Called once at startup, result cached and passed into every `build_sql_prompt()` call.

File format — comment-delimited:
```sql
-- Example: count students in a course per semester
SELECT COUNT(e.id) FROM enrollments e ...

-- Example: teacher with highest average grade
SELECT t.name, AVG(e.grade) ...
```

---

## 7. Tracing

### Two Layers, Linked by `trace_id`

| Concern | LangSmith | Structured Logs |
|---|---|---|
| LLM prompt snapshots | ✅ auto | — |
| Token usage / cost | ✅ auto | — |
| LLM latency | ✅ auto | — |
| Node routing decisions | — | ✅ |
| SQL generated | — | ✅ |
| DB result row count | — | ✅ |
| Retry attempts | — | ✅ |
| Ambiguity rounds | — | ✅ |
| Errors | — | ✅ |

### `Tracer` class (`agent/tracing.py`)

```python
class NodeEvent(str, Enum):
    START   = "start"
    END     = "end"
    ERROR   = "error"
    RETRY   = "retry"
    CLARIFY = "clarification_requested"
    SKIP    = "skip"

@dataclass
class Tracer:
    trace_id:   str
    session_id: str

    def log(self, node: str, event: NodeEvent, **kwargs) -> None:
        # emits structured JSON log line
```

- `Tracer` created at graph entry, stored in `AgentState`
- Every node calls `state["tracer"].log(...)` — one line per event
- LangSmith LLM calls tagged with `trace_id` via `config={"metadata": {"trace_id": ...}}`

### Log Format

```json
{"ts": "...", "trace_id": "a1b2", "session_id": "s1",
 "node": "sql_generator", "event": "end", "sql": "SELECT ..."}
```

---

## 8. Environment & Infrastructure

### `.env.example`

```bash
DB_DRIVER=postgres
POSTGRES_USER=university
POSTGRES_PASSWORD=university
POSTGRES_DB=university
POSTGRES_HOST=localhost
POSTGRES_PORT=5432

ANTHROPIC_API_KEY=...

LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=...
LANGCHAIN_PROJECT=university-qa-agent

LOG_LEVEL=INFO
MAX_CLARIFICATION_ROUNDS=3
MAX_SQL_RETRIES=2
CONVERSATION_HISTORY_WINDOW=6
DB_RESULTS_ROW_LIMIT=50
```

### `docker-compose.yml`

- Postgres 16 alpine
- Migrations in `db/migrations/` mounted to `/docker-entrypoint-initdb.d/` — auto-runs on first start

### `Makefile`

```makefile
run-db:   # docker compose up -d db + pg_isready health wait
run:      # depends on run-db, then uvicorn
test:     # DB_DRIVER=sqlite pytest tests/ -v
lint:     # ruff + mypy
```

`test` always overrides `DB_DRIVER=sqlite` — never touches real DB.

---

## 9. Unit Tests

### Layers

| Folder | What it tests |
|---|---|
| `test_db/` | Schema integrity, FK constraints, raw SQL query correctness |
| `test_agent/` | Each node in isolation with mocked LLM and mock tracer |
| `test_e2e/` | Full graph routing and state transitions with SQLite + mock LLM |

### Key test cases per node

**`test_sql_validator`** (pure Python, no mocks):
- SELECT passes, DROP/DELETE/INSERT/UPDATE/ALTER blocked
- Stacked statements blocked (`SELECT ...; DROP TABLE`)
- `information_schema` and `pg_catalog` access blocked
- Case-insensitive SELECT passes

**`test_question_analyzer`**:
- Answerable → status = "generating"
- Ambiguous → ambiguity_count increments, last_clarification set
- At limit → status = "error", answer contains "rephrase from scratch"
- Merger skipped on fresh question (LLM called once, not twice)
- Merger updates accumulated_intent on resume

**`test_sql_generator`**:
- Retry block absent on first attempt
- Retry block present with previous SQL + error on retry
- Schema context and few-shot examples injected into prompt

**`test_sql_executor`**:
- Empty result is not an error (status = "formatting")
- DB error triggers retry (status = "generating", retry_count incremented)
- Retry limit reached → status = "error"

**`test_few_shot_loader`**:
- Correct file loaded per driver
- postgres != sqlite content
- Unknown driver raises ValueError

### Fixtures

```python
# tests/conftest.py
sqlite_connector   # real SQLiteConnector(:memory:)
mock_llm           # MagicMock, set .return_value per test
mock_tracer        # MagicMock(spec=Tracer), log() is no-op
```

### Coverage targets

| Layer | Target |
|---|---|
| `test_db/` | 100% |
| `test_sql_validator` | 100% |
| `test_agent/` nodes | ~90% |
| `test_e2e/` | key routing paths |

---



---


