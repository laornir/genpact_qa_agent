"""E2E tests for the successful question → SQL → answer path."""

import json
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage


def _llm(
    classifier_status: str = "answerable", sql: str = "SELECT id, name FROM teachers"
) -> MagicMock:
    """Return a mock LLM wired for the happy path: classify → generate SQL → format answer."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(
                content=json.dumps(
                    {
                        "status": classifier_status,
                        "clarification_question": "",
                        "reason": "clear question",
                    }
                )
            ),
            AIMessage(content=sql),
            AIMessage(content="Alice Smith and Bob Jones are the teachers."),
        ]
    )
    return llm


async def test_happy_path_returns_200(test_app, client):
    """A well-formed question returns HTTP 200."""
    test_app.state.llm = _llm()
    resp = await client.post(
        "/chat", json={"session_id": "s-happy-1", "question": "List all teachers"}
    )
    assert resp.status_code == 200


async def test_happy_path_status_is_done(test_app, client):
    """The graph reaches 'done' status on a successful answerable question."""
    test_app.state.llm = _llm()
    body = (
        await client.post(
            "/chat", json={"session_id": "s-happy-2", "question": "List all teachers"}
        )
    ).json()
    assert body["status"] == "done"


async def test_happy_path_answer_is_populated(test_app, client):
    """The response contains a non-empty natural-language answer."""
    test_app.state.llm = _llm()
    body = (
        await client.post(
            "/chat", json={"session_id": "s-happy-3", "question": "List all teachers"}
        )
    ).json()
    assert body["answer"] is not None
    assert len(body["answer"]) > 0


async def test_happy_path_session_id_echoed(test_app, client):
    """The response echoes the client-supplied session_id."""
    test_app.state.llm = _llm()
    body = (
        await client.post(
            "/chat", json={"session_id": "s-happy-4", "question": "List all teachers"}
        )
    ).json()
    assert body["session_id"] == "s-happy-4"


async def test_happy_path_trace_id_present(test_app, client):
    """The response includes a non-empty trace_id for LangSmith correlation."""
    test_app.state.llm = _llm()
    body = (
        await client.post(
            "/chat", json={"session_id": "s-happy-5", "question": "List all teachers"}
        )
    ).json()
    assert body["trace_id"]


async def test_health_returns_ok(test_app, client):
    """GET /health returns status='ok' and db_ok=True for a seeded SQLite connector."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db_ok"] is True
