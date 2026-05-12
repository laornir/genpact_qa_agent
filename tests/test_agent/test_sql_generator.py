"""Tests for agent/nodes/sql_generator.py."""

from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from agent.nodes.sql_generator import sql_generator
from tests.test_agent.conftest import make_state

_FEW_SHOT = "-- Example: SELECT name FROM teachers"


def _config(llm: MagicMock) -> dict:
    return {"configurable": {"llm": llm, "few_shot_examples": _FEW_SHOT}}


def _messages_human(llm: MagicMock) -> str:
    """Extract the human message content from the first llm.ainvoke call."""
    call_args = llm.ainvoke.call_args[0][0]
    return next(m.content for m in call_args if isinstance(m, HumanMessage))


def _messages_system(llm: MagicMock) -> str:
    """Extract the system message content from the first llm.ainvoke call."""
    call_args = llm.ainvoke.call_args[0][0]
    return next(m.content for m in call_args if isinstance(m, SystemMessage))


# ---------------------------------------------------------------------------
# Basic behaviour
# ---------------------------------------------------------------------------


async def test_returns_sql_from_llm(mock_tracer):
    """sql_generator stores the LLM's output in state['sql']."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="SELECT * FROM teachers"))
    result = await sql_generator(
        make_state(mock_tracer, accumulated_intent="List all teachers"), _config(llm)
    )
    assert result["sql"] == "SELECT * FROM teachers"


async def test_sets_status_to_validating(mock_tracer):
    """sql_generator always advances status to 'validating'."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="SELECT 1"))
    result = await sql_generator(make_state(mock_tracer), _config(llm))
    assert result["status"] == "validating"


async def test_clears_sql_error(mock_tracer):
    """sql_generator resets sql_error to None on each run."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="SELECT 1"))
    state = make_state(
        mock_tracer, sql_error="syntax error", retry_count=1, sql="SELECT * FORM teachers"
    )
    result = await sql_generator(state, _config(llm))
    assert result["sql_error"] is None


# ---------------------------------------------------------------------------
# Prompt content
# ---------------------------------------------------------------------------


async def test_schema_context_in_system_prompt(mock_tracer):
    """Schema context is injected into the system message."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="SELECT 1"))
    state = make_state(mock_tracer, schema_context="teachers: id, name")
    await sql_generator(state, _config(llm))
    assert "teachers: id, name" in _messages_system(llm)


async def test_few_shot_examples_in_system_prompt(mock_tracer):
    """Few-shot examples are injected into the system message."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="SELECT 1"))
    await sql_generator(make_state(mock_tracer), _config(llm))
    assert _FEW_SHOT in _messages_system(llm)


# ---------------------------------------------------------------------------
# Retry block
# ---------------------------------------------------------------------------


async def test_retry_block_absent_on_first_attempt(mock_tracer):
    """No retry context in the human message when retry_count is 0."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="SELECT 1"))
    await sql_generator(make_state(mock_tracer, retry_count=0), _config(llm))
    human = _messages_human(llm)
    assert "Previous attempt" not in human


async def test_retry_block_present_on_retry(mock_tracer):
    """Previous SQL and error message appear in the human message on retry."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="SELECT * FROM teachers WHERE id = 1"))
    state = make_state(
        mock_tracer,
        retry_count=1,
        sql="SELECT * FORM teachers",
        sql_error="near 'FORM': syntax error",
        accumulated_intent="Who are the teachers?",
    )
    await sql_generator(state, _config(llm))
    human = _messages_human(llm)
    assert "SELECT * FORM teachers" in human
    assert "near 'FORM': syntax error" in human


async def test_retry_block_includes_correction_instruction(mock_tracer):
    """The retry human message instructs the LLM to generate a corrected query."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=AIMessage(content="SELECT 1"))
    state = make_state(mock_tracer, retry_count=1, sql="bad", sql_error="err")
    await sql_generator(state, _config(llm))
    assert "corrected" in _messages_human(llm).lower()
