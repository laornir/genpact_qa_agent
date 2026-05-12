"""Shared helpers for agent node tests."""

from agent.state import AgentState


def make_state(mock_tracer, **overrides) -> AgentState:
    """
    Build a baseline AgentState dict for use in node unit tests.

    All optional fields default to their "fresh question" / "nothing yet"
    values.  Pass keyword arguments to override specific fields.

    Args:
        mock_tracer: The ``mock_tracer`` fixture from ``tests/conftest.py``.
        **overrides: Any AgentState field values to override.

    Returns:
        A fully populated AgentState-compatible dict.
    """
    base: AgentState = {
        "question": "Who teaches Algorithms?",
        "schema_context": "teachers: id, name, email\ncourses: id, name, credits",
        "sql": None,
        "sql_error": None,
        "retry_count": 0,
        "db_results": None,
        "answer": None,
        "status": "analyzing",
        "conversation_history": [],
        "accumulated_intent": None,
        "last_clarification": None,
        "ambiguity_count": 0,
        "trace_id": "trace-test",
        "session_id": "session-test",
        "tracer": mock_tracer,
    }
    return {**base, **overrides}  # type: ignore[return-value]
