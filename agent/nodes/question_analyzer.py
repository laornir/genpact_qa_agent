"""
Question-analyzer node — the entry point of every graph run.

Responsibilities:
1. **Intent merger** (only when resuming a clarification turn): calls the
   merger LLM to combine the previous ``accumulated_intent`` with the user's
   new answer into a single updated intent string.
2. **Intent classifier**: classifies the (possibly merged) intent as
   ``answerable``, ``ambiguous``, or ``out_of_scope`` and routes accordingly.

Fresh-question detection is driven by ``state["last_clarification"]``:
- ``None``  → fresh question; skip the merger, use the raw question as intent.
- ``str``   → clarification continuation; run the merger first.

See ``agent/prompts/question_analyzer.py`` for the prompt implementations and
the approved plan for the full design rationale.

Usage::

    from agent.nodes.question_analyzer import question_analyzer

Settings used (via ``config["configurable"]``):
    llm                     -- LangChain chat model instance
    max_clarification_rounds -- int, default 3
"""

import json

from langchain_core.runnables import RunnableConfig

from agent.prompts.question_analyzer import build_classifier_prompt, build_merger_prompt
from agent.state import AgentState
from agent.tracing import NodeEvent


async def question_analyzer(state: AgentState, config: RunnableConfig) -> dict:
    """
    LangGraph node: classify the user's intent and set the routing status.

    Calls the merger LLM prompt when resuming a clarification turn, then
    always calls the classifier prompt.  Returns a partial state update that
    drives graph routing via ``state["status"]``.

    Args:
        state:  Current AgentState.
        config: LangGraph RunnableConfig; must contain
                ``config["configurable"]["llm"]`` and optionally
                ``config["configurable"]["max_clarification_rounds"]``.

    Returns:
        Partial state dict with at minimum ``status`` and ``accumulated_intent``.
    """
    tracer = state["tracer"]
    tracer.log("question_analyzer", NodeEvent.START)

    llm = config["configurable"]["llm"]
    max_rounds: int = config["configurable"].get("max_clarification_rounds", 3)

    # ── Step 1: intent merger (clarification continuation only) ──────────────
    if state["last_clarification"] is not None:
        merger_messages = build_merger_prompt(
            accumulated_intent=state["accumulated_intent"],
            last_clarification=state["last_clarification"],
            current_input=state["question"],
        )
        merged = await llm.ainvoke(merger_messages)
        accumulated_intent: str = merged.content.strip()
    else:
        # Fresh question: initialise intent from the raw question
        accumulated_intent = state["accumulated_intent"] or state["question"]

    # ── Step 2: classifier ───────────────────────────────────────────────────
    classifier_messages = build_classifier_prompt(
        accumulated_intent=accumulated_intent,
        schema_context=state["schema_context"],
    )
    raw = await llm.ainvoke(classifier_messages)

    try:
        parsed: dict = json.loads(raw.content)
    except (json.JSONDecodeError, AttributeError):
        tracer.log("question_analyzer", NodeEvent.ERROR, reason="invalid_classifier_json")
        return {
            "status": "error",
            "answer": "Failed to classify the question.",
            "accumulated_intent": accumulated_intent,
        }

    classification = parsed.get("status", "out_of_scope")

    # ── Step 3: route ────────────────────────────────────────────────────────
    if classification == "answerable":
        tracer.log("question_analyzer", NodeEvent.END, status="generating")
        return {
            "status": "generating",
            "accumulated_intent": accumulated_intent,
            "last_clarification": None,  # resolution: reset sentinel
            "ambiguity_count": 0,  # resolution: reset counter
        }

    if classification == "ambiguous" and state["ambiguity_count"] < max_rounds:
        clarification_q = parsed.get("clarification_question", "Could you clarify your question?")
        new_count = state["ambiguity_count"] + 1
        tracer.log("question_analyzer", NodeEvent.CLARIFY, ambiguity_count=new_count)
        return {
            "status": "asking_clarification",
            "accumulated_intent": accumulated_intent,
            "last_clarification": clarification_q,
            "ambiguity_count": new_count,
            "answer": clarification_q,
        }

    if classification == "ambiguous":  # at limit
        tracer.log("question_analyzer", NodeEvent.ERROR, reason="ambiguity_limit_reached")
        return {
            "status": "error",
            "answer": "Too many ambiguous questions, please rephrase from scratch.",
            "accumulated_intent": accumulated_intent,
        }

    # out_of_scope (and any unexpected value)
    reason = parsed.get("reason", "This question is outside the scope of the system.")
    tracer.log("question_analyzer", NodeEvent.END, status="error", reason=reason)
    return {
        "status": "error",
        "answer": reason,
        "accumulated_intent": accumulated_intent,
    }
