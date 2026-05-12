"""E2E tests for the SQL error → retry path."""

import json
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage


async def test_db_error_retries_and_succeeds(test_app, client):
    """A DB error on first SQL attempt triggers a retry that succeeds."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(
                content=json.dumps(
                    {  # classifier
                        "status": "answerable",
                        "clarification_question": "",
                        "reason": "clear",
                    }
                )
            ),
            AIMessage(content="SELECT * FROM nonexistent_table"),  # sql_generator (fails at DB)
            AIMessage(content="SELECT id, name FROM teachers"),  # sql_generator retry
            AIMessage(content="Alice Smith and Bob Jones."),  # answer_formatter
        ]
    )
    test_app.state.llm = llm

    body = (
        await client.post(
            "/chat",
            json={
                "session_id": "s-retry-1",
                "question": "List all teachers",
            },
        )
    ).json()

    assert body["status"] == "done"


async def test_retry_exhausted_returns_error(test_app, client):
    """Exhausting all SQL retries results in status='error'."""
    llm = MagicMock()
    # classifier + sql_generator called once per attempt (1 initial + 2 retries = 3 sql calls)
    llm.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(
                content=json.dumps(
                    {
                        "status": "answerable",
                        "clarification_question": "",
                        "reason": "clear",
                    }
                )
            ),
            AIMessage(content="SELECT * FROM nonexistent_table"),  # attempt 1
            AIMessage(content="SELECT * FROM nonexistent_table"),  # attempt 2
            AIMessage(content="SELECT * FROM nonexistent_table"),  # attempt 3 (at limit)
        ]
    )
    test_app.state.llm = llm

    body = (
        await client.post(
            "/chat",
            json={
                "session_id": "s-retry-2",
                "question": "List all teachers",
            },
        )
    ).json()

    assert body["status"] == "error"
    assert body["answer"] is not None
