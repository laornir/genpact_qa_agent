"""Tests for agent/nodes/question_analyzer.py."""

import json
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import AIMessage

from agent.nodes.question_analyzer import question_analyzer
from tests.test_agent.conftest import make_state

_CONFIG_BASE = {"configurable": {"max_clarification_rounds": 3}}


def _config(llm: MagicMock) -> dict:
    return {"configurable": {"llm": llm, "max_clarification_rounds": 3}}


def _answerable_response() -> AIMessage:
    return AIMessage(
        content=json.dumps(
            {
                "status": "answerable",
                "clarification_question": "",
                "reason": "clear question",
            }
        )
    )


def _ambiguous_response(q: str = "Which semester?") -> AIMessage:
    return AIMessage(
        content=json.dumps(
            {
                "status": "ambiguous",
                "clarification_question": q,
                "reason": "semester not specified",
            }
        )
    )


def _out_of_scope_response() -> AIMessage:
    return AIMessage(
        content=json.dumps(
            {
                "status": "out_of_scope",
                "clarification_question": "",
                "reason": "Cannot answer from this DB",
            }
        )
    )


# ---------------------------------------------------------------------------
# Routing: answerable
# ---------------------------------------------------------------------------


async def test_answerable_sets_generating(mock_tracer):
    """Answerable classification sets status to 'generating'."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_answerable_response())
    result = await question_analyzer(make_state(mock_tracer), _config(llm))
    assert result["status"] == "generating"


async def test_answerable_resets_clarification_fields(mock_tracer):
    """On resolution, last_clarification and ambiguity_count are reset to None/0."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_answerable_response())
    state = make_state(mock_tracer, last_clarification="Which semester?", ambiguity_count=1)
    result = await question_analyzer(state, _config(llm))
    assert result["last_clarification"] is None
    assert result["ambiguity_count"] == 0


# ---------------------------------------------------------------------------
# Routing: ambiguous
# ---------------------------------------------------------------------------


async def test_ambiguous_sets_asking_clarification(mock_tracer):
    """Ambiguous classification sets status to 'asking_clarification'."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_ambiguous_response())
    result = await question_analyzer(make_state(mock_tracer), _config(llm))
    assert result["status"] == "asking_clarification"


async def test_ambiguous_increments_ambiguity_count(mock_tracer):
    """ambiguity_count increments by 1 on each clarification round."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_ambiguous_response())
    result = await question_analyzer(make_state(mock_tracer, ambiguity_count=1), _config(llm))
    assert result["ambiguity_count"] == 2


async def test_ambiguous_sets_last_clarification(mock_tracer):
    """last_clarification is set to the clarification_question from the classifier."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_ambiguous_response("Which year?"))
    result = await question_analyzer(make_state(mock_tracer), _config(llm))
    assert result["last_clarification"] == "Which year?"


async def test_ambiguous_at_limit_sets_error(mock_tracer):
    """When ambiguity_count equals max_clarification_rounds, status becomes 'error'."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_ambiguous_response())
    state = make_state(mock_tracer, ambiguity_count=3)
    result = await question_analyzer(state, _config(llm))
    assert result["status"] == "error"


async def test_ambiguous_at_limit_answer_contains_rephrase(mock_tracer):
    """The error answer tells the user to rephrase from scratch."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_ambiguous_response())
    state = make_state(mock_tracer, ambiguity_count=3)
    result = await question_analyzer(state, _config(llm))
    assert "rephrase from scratch" in result["answer"]


# ---------------------------------------------------------------------------
# Routing: out_of_scope
# ---------------------------------------------------------------------------


async def test_out_of_scope_sets_error(mock_tracer):
    """Out-of-scope classification sets status to 'error'."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_out_of_scope_response())
    result = await question_analyzer(make_state(mock_tracer), _config(llm))
    assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Fresh question vs clarification continuation
# ---------------------------------------------------------------------------


async def test_merger_skipped_on_fresh_question(mock_tracer):
    """LLM is called exactly once (classifier only) when last_clarification is None."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_answerable_response())
    await question_analyzer(make_state(mock_tracer, last_clarification=None), _config(llm))
    assert llm.ainvoke.call_count == 1


async def test_merger_called_on_clarification_resume(mock_tracer):
    """LLM is called twice (merger + classifier) when last_clarification is set."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(content="User wants Algorithms teacher in Fall 2024"),  # merger
            _answerable_response(),  # classifier
        ]
    )
    state = make_state(
        mock_tracer,
        last_clarification="Which semester?",
        accumulated_intent="Who teaches Algorithms?",
        ambiguity_count=1,
    )
    await question_analyzer(state, _config(llm))
    assert llm.ainvoke.call_count == 2


async def test_merger_updates_accumulated_intent(mock_tracer):
    """accumulated_intent is overwritten with the merger LLM's output on resume."""
    llm = MagicMock()
    merged_intent = "User wants Algorithms teacher in Fall 2024"
    llm.ainvoke = AsyncMock(
        side_effect=[
            AIMessage(content=merged_intent),
            _answerable_response(),
        ]
    )
    state = make_state(
        mock_tracer,
        last_clarification="Which semester?",
        accumulated_intent="Who teaches Algorithms?",
        ambiguity_count=1,
    )
    result = await question_analyzer(state, _config(llm))
    assert result["accumulated_intent"] == merged_intent


async def test_fresh_question_uses_raw_question_as_intent(mock_tracer):
    """On a fresh question with no prior intent, accumulated_intent is set from question."""
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=_answerable_response())
    state = make_state(mock_tracer, question="Who teaches Databases?", accumulated_intent=None)
    result = await question_analyzer(state, _config(llm))
    assert result["accumulated_intent"] == "Who teaches Databases?"
