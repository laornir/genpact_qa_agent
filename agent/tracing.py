"""
Structured logging and LangSmith tracing infrastructure for the agent graph.

Two complementary layers are used together, linked by ``trace_id``:

- **LangSmith** — captures LLM prompt snapshots, token usage, and latency
  automatically when ``LANGCHAIN_TRACING_V2=true``. Node code tags each LLM
  call with the trace_id via ``config={"metadata": {"trace_id": ...}}``.

- **Structured logs** — emitted by ``Tracer.log()`` for every routing decision,
  SQL query, retry attempt, clarification round, and error. Each line is a
  single JSON object written to the configured Python logger.

A ``Tracer`` instance is created once at graph entry and stored in
``AgentState`` so every node can call ``state["tracer"].log(...)`` without
any additional setup.

Usage::

    from agent.tracing import Tracer, NodeEvent, setup_logging

    setup_logging("INFO")                          # once at app startup
    tracer = Tracer(trace_id="abc", session_id="s1")
    tracer.log("sql_generator", NodeEvent.END, sql="SELECT 1")
    # → {"ts": "...", "trace_id": "abc", "session_id": "s1",
    #    "node": "sql_generator", "event": "end", "sql": "SELECT 1"}

Settings used:
    LOG_LEVEL -- passed to setup_logging() during FastAPI lifespan startup.
"""

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

_logger = logging.getLogger("university_qa")


class NodeEvent(StrEnum):
    """Lifecycle events emitted by agent nodes."""

    START = "start"
    END = "end"
    ERROR = "error"
    RETRY = "retry"
    CLARIFY = "clarification_requested"
    SKIP = "skip"


@dataclass
class Tracer:
    """
    Emits one structured JSON log line per agent node event.

    A single instance is created at graph entry and stored in ``AgentState``.
    All fields are fixed at construction; only ``node`` and ``event`` vary
    per call.
    """

    trace_id: str
    session_id: str

    def log(self, node: str, event: NodeEvent, **kwargs: object) -> None:
        """
        Emit a structured JSON log line for a node lifecycle event.

        The line always contains ``ts``, ``trace_id``, ``session_id``,
        ``node``, and ``event``. Any additional keyword arguments (e.g.
        ``sql``, ``retry_count``, ``row_count``) are merged in as extra
        fields so callers can attach relevant context without a fixed schema.

        Args:
            node:   Name of the agent node emitting the event
                    (e.g. ``"sql_generator"``).
            event:  Lifecycle stage described by the log line.
            **kwargs: Arbitrary extra fields to include in the JSON record.
        """
        record: dict[str, object] = {
            "ts": datetime.now(UTC).isoformat(),
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "node": node,
            "event": event.value,
            **kwargs,
        }
        _logger.info(json.dumps(record))


def setup_logging(level: str = "INFO") -> None:
    """
    Configure the ``university_qa`` logger to emit plain JSON lines to stdout.

    Should be called once during FastAPI lifespan startup. Safe to call
    multiple times — additional handlers are not added on repeat calls.

    Args:
        level: Logging level string (e.g. ``"INFO"``, ``"DEBUG"``).
               Matched case-insensitively. Defaults to ``"INFO"``.
    """
    if not _logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        _logger.addHandler(handler)
    _logger.setLevel(level.upper())
    _logger.propagate = False
