"""E2E tests for the out-of-scope routing path."""

import json
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage


async def test_out_of_scope_returns_error_status(test_app, client):
    """An out-of-scope classification routes to status='error' without running SQL."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "status": "out_of_scope",
                    "clarification_question": "",
                    "reason": "The question is not answerable from the university database.",
                }
            )
        )
    )
    test_app.state.llm = llm

    body = (
        await client.post(
            "/chat",
            json={
                "session_id": "s-oos-1",
                "question": "What is the weather in New York?",
            },
        )
    ).json()

    assert body["status"] == "error"


async def test_out_of_scope_llm_called_once(test_app, client):
    """The LLM is called exactly once (classifier only) for an out-of-scope question."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "status": "out_of_scope",
                    "clarification_question": "",
                    "reason": "Not a university question.",
                }
            )
        )
    )
    test_app.state.llm = llm

    await client.post(
        "/chat",
        json={
            "session_id": "s-oos-2",
            "question": "Who is the president?",
        },
    )

    assert llm.ainvoke.call_count == 1


async def test_out_of_scope_answer_is_populated(test_app, client):
    """The response answer is non-empty so the client can display it to the user."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "status": "out_of_scope",
                    "clarification_question": "",
                    "reason": "Not answerable from this database.",
                }
            )
        )
    )
    test_app.state.llm = llm

    body = (
        await client.post(
            "/chat",
            json={
                "session_id": "s-oos-3",
                "question": "What is 2+2?",
            },
        )
    ).json()

    assert body["answer"] is not None
