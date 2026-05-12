"""Tests for agent/state.py — AgentState TypedDict shape and AgentStatus values."""

from typing import get_args

from agent.state import AgentState, AgentStatus

# ---------------------------------------------------------------------------
# Expected field and status definitions — single source of truth for tests
# ---------------------------------------------------------------------------

CORE_FIELDS = {
    "question",
    "schema_context",
    "sql",
    "sql_error",
    "retry_count",
    "db_results",
    "answer",
    "status",
}
MULTI_TURN_FIELDS = {
    "conversation_history",
    "accumulated_intent",
    "last_clarification",
    "ambiguity_count",
}
TRACING_FIELDS = {"trace_id", "session_id", "tracer"}
ALL_FIELDS = CORE_FIELDS | MULTI_TURN_FIELDS | TRACING_FIELDS

EXPECTED_STATUSES = {
    "analyzing",
    "generating",
    "validating",
    "executing",
    "formatting",
    "asking_clarification",
    "error",
    "done",
}


# ---------------------------------------------------------------------------
# AgentStatus
# ---------------------------------------------------------------------------


def test_agent_status_has_all_expected_values():
    """AgentStatus Literal contains exactly the eight documented status strings."""
    assert set(get_args(AgentStatus)) == EXPECTED_STATUSES


def test_agent_status_has_no_extra_values():
    """AgentStatus contains no undocumented status values."""
    assert len(get_args(AgentStatus)) == len(EXPECTED_STATUSES)


# ---------------------------------------------------------------------------
# AgentState field presence
# ---------------------------------------------------------------------------


def test_agent_state_has_all_fields():
    """AgentState defines exactly the full set of expected fields."""
    assert set(AgentState.__annotations__) == ALL_FIELDS


def test_agent_state_has_all_core_fields():
    """AgentState includes every core pipeline field."""
    assert CORE_FIELDS.issubset(AgentState.__annotations__)


def test_agent_state_has_all_multi_turn_fields():
    """AgentState includes every multi-turn conversation tracking field."""
    assert MULTI_TURN_FIELDS.issubset(AgentState.__annotations__)


def test_agent_state_has_all_tracing_fields():
    """AgentState includes every tracing field."""
    assert TRACING_FIELDS.issubset(AgentState.__annotations__)


# ---------------------------------------------------------------------------
# AgentState construction — valid dicts
# ---------------------------------------------------------------------------


def _make_state(mock_tracer, **overrides) -> AgentState:
    base: AgentState = {
        "question": "Who teaches Algorithms?",
        "schema_context": "teachers: id, name",
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
        "trace_id": "trace-abc",
        "session_id": "session-xyz",
        "tracer": mock_tracer,
    }
    return {**base, **overrides}  # type: ignore[return-value]


def test_valid_initial_state_can_be_constructed(mock_tracer):
    """A freshly created AgentState with all None optionals is a valid dict."""
    state = _make_state(mock_tracer)
    assert state["question"] == "Who teaches Algorithms?"
    assert state["status"] == "analyzing"
    assert state["retry_count"] == 0
    assert state["ambiguity_count"] == 0


def test_nullable_fields_accept_none(mock_tracer):
    """All optional fields can be set to None without error."""
    state = _make_state(mock_tracer)
    for field in (
        "sql",
        "sql_error",
        "db_results",
        "answer",
        "accumulated_intent",
        "last_clarification",
    ):
        assert state[field] is None


def test_state_with_sql_populated(mock_tracer):
    """AgentState accepts a non-None sql value after the generator node runs."""
    state = _make_state(mock_tracer, sql="SELECT * FROM teachers", status="validating")
    assert state["sql"] == "SELECT * FROM teachers"
    assert state["status"] == "validating"


def test_state_with_db_results(mock_tracer):
    """AgentState accepts a list of row dicts in db_results after execution."""
    results = [{"name": "Alice"}, {"name": "Bob"}]
    state = _make_state(mock_tracer, db_results=results, status="formatting")
    assert state["db_results"] == results
    assert state["status"] == "formatting"


def test_state_with_conversation_history(mock_tracer):
    """conversation_history accepts a list of role/content turn dicts."""
    history = [
        {"role": "user", "content": "Who teaches Algorithms?"},
        {"role": "assistant", "content": "Alice Smith."},
    ]
    state = _make_state(mock_tracer, conversation_history=history)
    assert len(state["conversation_history"]) == 2


def test_state_retry_count_increments(mock_tracer):
    """retry_count can be set to values greater than zero for retry scenarios."""
    state = _make_state(mock_tracer, retry_count=2, sql_error="syntax error")
    assert state["retry_count"] == 2
    assert state["sql_error"] == "syntax error"


def test_state_clarification_fields(mock_tracer):
    """Clarification fields are set correctly when the agent asks for more detail."""
    state = _make_state(
        mock_tracer,
        status="asking_clarification",
        last_clarification="Which semester do you mean?",
        ambiguity_count=1,
        accumulated_intent="Student count for a specific semester",
    )
    assert state["status"] == "asking_clarification"
    assert state["ambiguity_count"] == 1
    assert state["last_clarification"] == "Which semester do you mean?"
    assert state["accumulated_intent"] is not None


def test_tracer_stored_in_state(mock_tracer):
    """The Tracer instance is stored and retrievable from the state dict."""
    state = _make_state(mock_tracer)
    assert state["tracer"] is mock_tracer
