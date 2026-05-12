"""Tests for agent/nodes/sql_executor.py."""

from unittest.mock import AsyncMock, MagicMock

from agent.nodes.sql_executor import sql_executor
from tests.test_agent.conftest import make_state


def _config(connector: MagicMock, max_retries: int = 2) -> dict:
    return {"configurable": {"connector": connector, "max_sql_retries": max_retries}}


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


async def test_success_sets_formatting(mock_tracer):
    """sql_executor sets status to 'formatting' when the query succeeds."""
    connector = MagicMock()
    connector.execute_query = AsyncMock(return_value=[{"name": "Alice"}])
    state = make_state(mock_tracer, sql="SELECT name FROM teachers")
    result = await sql_executor(state, _config(connector))
    assert result["status"] == "formatting"


async def test_success_stores_db_results(mock_tracer):
    """db_results is populated with the rows returned by the connector."""
    rows = [{"name": "Alice"}, {"name": "Bob"}]
    connector = MagicMock()
    connector.execute_query = AsyncMock(return_value=rows)
    state = make_state(mock_tracer, sql="SELECT name FROM teachers")
    result = await sql_executor(state, _config(connector))
    assert result["db_results"] == rows


async def test_empty_result_is_not_an_error(mock_tracer):
    """An empty result set is a valid success — status should be 'formatting'."""
    connector = MagicMock()
    connector.execute_query = AsyncMock(return_value=[])
    state = make_state(mock_tracer, sql="SELECT * FROM teachers WHERE id = 9999")
    result = await sql_executor(state, _config(connector))
    assert result["status"] == "formatting"
    assert result["db_results"] == []


async def test_success_clears_sql_error(mock_tracer):
    """sql_error is reset to None on a successful execution."""
    connector = MagicMock()
    connector.execute_query = AsyncMock(return_value=[])
    state = make_state(mock_tracer, sql="SELECT 1", sql_error="previous error")
    result = await sql_executor(state, _config(connector))
    assert result["sql_error"] is None


# ---------------------------------------------------------------------------
# Error / retry path
# ---------------------------------------------------------------------------


async def test_db_error_triggers_retry(mock_tracer):
    """A DB exception sets status to 'generating' and increments retry_count."""
    connector = MagicMock()
    connector.execute_query = AsyncMock(side_effect=Exception("syntax error"))
    state = make_state(mock_tracer, sql="SELECT * FORM teachers", retry_count=0)
    result = await sql_executor(state, _config(connector, max_retries=2))
    assert result["status"] == "generating"
    assert result["retry_count"] == 1


async def test_db_error_stores_error_message(mock_tracer):
    """The DB error message is stored in sql_error for use by sql_generator on retry."""
    connector = MagicMock()
    connector.execute_query = AsyncMock(side_effect=Exception("near 'FORM': syntax error"))
    state = make_state(mock_tracer, sql="bad", retry_count=0)
    result = await sql_executor(state, _config(connector, max_retries=2))
    assert "syntax error" in result["sql_error"]


async def test_retry_limit_reached_sets_error(mock_tracer):
    """Status becomes 'error' when retry_count already equals max_sql_retries."""
    connector = MagicMock()
    connector.execute_query = AsyncMock(side_effect=Exception("still broken"))
    state = make_state(mock_tracer, sql="bad", retry_count=2)
    result = await sql_executor(state, _config(connector, max_retries=2))
    assert result["status"] == "error"


async def test_retry_limit_reached_sets_answer(mock_tracer):
    """An answer message is set when the retry limit is exhausted."""
    connector = MagicMock()
    connector.execute_query = AsyncMock(side_effect=Exception("broken"))
    state = make_state(mock_tracer, sql="bad", retry_count=2)
    result = await sql_executor(state, _config(connector, max_retries=2))
    assert result.get("answer") is not None
