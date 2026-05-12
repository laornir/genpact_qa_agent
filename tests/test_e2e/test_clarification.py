"""E2E tests for the multi-turn clarification path."""

import json
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage


async def test_ambiguous_question_returns_asking_clarification(test_app, client):
    """An ambiguous question routes to asking_clarification and returns the question text."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "status": "ambiguous",
                    "clarification_question": "Which semester are you asking about?",
                    "reason": "semester unspecified",
                }
            )
        )
    )
    test_app.state.llm = llm

    body = (
        await client.post(
            "/chat",
            json={
                "session_id": "s-clar-1",
                "question": "Who teaches Algorithms?",
            },
        )
    ).json()

    assert body["status"] == "asking_clarification"
    assert "semester" in (body["answer"] or "").lower()


async def test_clarification_followup_resolves_to_done(test_app, client):
    """After a clarification answer the graph completes with status='done'."""
    session_id = "s-clar-2"

    # Turn 1: ambiguous
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "status": "ambiguous",
                    "clarification_question": "Which semester?",
                    "reason": "unspecified",
                }
            )
        )
    )
    test_app.state.llm = llm
    await client.post(
        "/chat", json={"session_id": session_id, "question": "Who teaches Algorithms?"}
    )

    # Turn 2: user answers, graph resolves
    llm2 = MagicMock()
    llm2.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(content="User wants to know who teaches Algorithms in Fall 2024"),  # merger
            AIMessage(
                content=json.dumps(
                    {
                        "status": "answerable",
                        "clarification_question": "",
                        "reason": "clear",
                    }
                )
            ),  # classifier
            AIMessage(
                content="SELECT t.name FROM teachers t "
                "JOIN course_offerings co ON co.teacher_id = t.id "
                "JOIN courses c ON c.id = co.course_id "
                "JOIN semesters s ON s.id = co.semester_id "
                "WHERE c.name = 'Algorithms' AND s.name = 'Fall 2024'"
            ),  # sql_generator
            AIMessage(content="Alice Smith teaches Algorithms in Fall 2024."),  # answer_formatter
        ]
    )
    test_app.state.llm = llm2
    body = (
        await client.post(
            "/chat",
            json={
                "session_id": session_id,
                "question": "Fall 2024",
            },
        )
    ).json()

    assert body["status"] == "done"


async def test_clarification_answer_is_the_question_asked(test_app, client):
    """On asking_clarification the answer field contains the clarification question."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        return_value=AIMessage(
            content=json.dumps(
                {
                    "status": "ambiguous",
                    "clarification_question": "Did you mean Fall or Spring semester?",
                    "reason": "season missing",
                }
            )
        )
    )
    test_app.state.llm = llm

    body = (
        await client.post(
            "/chat",
            json={
                "session_id": "s-clar-3",
                "question": "List courses in 2024",
            },
        )
    ).json()

    assert body["answer"] == "Did you mean Fall or Spring semester?"


async def test_clarification_limit_returns_error(test_app, client):
    """Reaching max_clarification_rounds results in status='error'.

    With max_clarification_rounds=3 the count reaches 3 after the third
    ambiguous turn; the fourth turn checks 3 < 3 == False and routes to error.
    """
    session_id = "s-clar-4"
    ambiguous_response = AIMessage(
        content=json.dumps(
            {
                "status": "ambiguous",
                "clarification_question": "Which semester?",
                "reason": "unspecified",
            }
        )
    )

    # 4 turns: 3 increment the counter (0→1, 1→2, 2→3), the 4th hits the limit
    questions = ["Who teaches?", "Maybe Fall", "Still unclear", "I give up"]
    for i, question in enumerate(questions):
        llm = MagicMock()
        if i == 0:
            llm.ainvoke = AsyncMock(return_value=ambiguous_response)
        else:
            llm.ainvoke = AsyncMock(
                side_effect=[
                    AIMessage(content="merged intent"),
                    ambiguous_response,
                ]
            )
        test_app.state.llm = llm
        body = (
            await client.post("/chat", json={"session_id": session_id, "question": question})
        ).json()

    assert body["status"] == "error"
    assert "rephrase from scratch" in (body["answer"] or "")
