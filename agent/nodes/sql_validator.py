"""
SQL safety validator — pure Python, no LLM.

Provides ``validate_sql`` (a standalone function usable in tests) and the
``sql_validator`` LangGraph node that calls it and writes the routing status
back into agent state.

The validator applies four guards in order:
1. **SELECT/WITH whitelist** — the query must start with SELECT or WITH (for
   CTEs); anything else (CALL, SHOW, …) is rejected immediately.
2. **Stacked statements** — a semicolon that remains after stripping the
   trailing one signals multiple statements, which are always blocked.
3. **Blocked DML/DDL keywords** — prevents data modification or schema changes.
4. **Blocked system schemas** — prevents introspection of ``information_schema``
   or ``pg_catalog``, which could leak DB internals.

Usage::

    from agent.nodes.sql_validator import validate_sql, sql_validator

Settings used:
    None — this node is stateless and reads only from AgentState.
"""

import re

from agent.state import AgentState
from agent.tracing import NodeEvent

_BLOCKED_KEYWORDS = re.compile(
    r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|REPLACE|MERGE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)
_BLOCKED_SCHEMAS = re.compile(
    r"\b(information_schema|pg_catalog)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str) -> tuple[bool, str | None]:
    """
    Check whether a SQL string is safe to execute against the university DB.

    Validation is intentionally strict: any doubt results in rejection.
    The guards run in order; the first failure short-circuits the rest.
    Only SELECT and WITH (CTE) are whitelisted as the opening keyword.

    Args:
        sql: The SQL string to validate (may include leading/trailing whitespace).

    Returns:
        A ``(is_valid, error_message)`` tuple.  ``error_message`` is None when
        ``is_valid`` is True.
    """
    # Guard 1: must start with SELECT or WITH (CTE)
    normalised = sql.strip().lstrip("(").upper()
    if not (normalised.startswith("SELECT") or normalised.startswith("WITH")):
        return False, "Only SELECT queries are permitted"

    # Guard 2: stacked statements
    stripped = sql.strip().rstrip(";")
    if ";" in stripped:
        return False, "Multiple statements are not allowed"

    # Guard 3: blocked DML / DDL keywords
    match = _BLOCKED_KEYWORDS.search(sql)
    if match:
        return False, f"Statement type '{match.group()}' is not allowed"

    # Guard 4: blocked system schemas
    match = _BLOCKED_SCHEMAS.search(sql)
    if match:
        return False, f"Access to '{match.group()}' is not allowed"

    return True, None


def sql_validator(state: AgentState) -> dict:
    """
    LangGraph node: validate the generated SQL and set the routing status.

    Reads ``state["sql"]``, calls ``validate_sql``, and returns a partial
    state update.  On success the status advances to ``"executing"``; on
    failure it becomes ``"error"`` with a user-facing message in ``answer``.

    Args:
        state: Current AgentState; reads ``sql`` and ``tracer``.

    Returns:
        Partial state dict with ``status`` and optionally ``answer``.
    """
    tracer = state["tracer"]
    tracer.log("sql_validator", NodeEvent.START)

    sql = state["sql"] or ""
    is_valid, error_msg = validate_sql(sql)

    if is_valid:
        tracer.log("sql_validator", NodeEvent.END, valid=True)
        return {"status": "executing"}

    tracer.log("sql_validator", NodeEvent.ERROR, reason=error_msg)
    return {
        "status": "error",
        "answer": f"Generated SQL failed safety validation: {error_msg}",
    }
