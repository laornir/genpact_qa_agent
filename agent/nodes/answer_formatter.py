"""
Answer-formatter node — converts raw DB results to natural language.

Truncates results to ``db_results_row_limit`` rows before sending to the LLM
to keep token usage bounded.  The LLM is instructed to answer in plain English
without mentioning SQL or databases.

Usage::

    from agent.nodes.answer_formatter import answer_formatter

Settings used (via ``config["configurable"]``):
    llm                  -- LangChain chat model instance
    db_results_row_limit -- int, default 50
"""

from langchain_core.runnables import RunnableConfig

from agent.prompts.answer_formatter import build_answer_prompt
from agent.prompts.helpers import format_db_results, truncate_results
from agent.state import AgentState
from agent.tracing import NodeEvent


async def answer_formatter(state: AgentState, config: RunnableConfig) -> dict:
    """
    LangGraph node: format DB results as a natural-language answer.

    Truncates the result set, serialises it to JSON, then calls the LLM.
    Always advances status to ``"done"``.

    Args:
        state:  Current AgentState; reads ``question``, ``db_results``, and ``tracer``.
        config: LangGraph RunnableConfig; must contain
                ``config["configurable"]["llm"]`` and optionally
                ``config["configurable"]["db_results_row_limit"]``.

    Returns:
        Partial state dict with ``answer`` and ``status = "done"``.
    """
    tracer = state["tracer"]
    tracer.log("answer_formatter", NodeEvent.START)

    llm = config["configurable"]["llm"]
    row_limit: int = config["configurable"].get("db_results_row_limit", 50)

    results = truncate_results(state["db_results"] or [], row_limit)
    results_str = format_db_results(results)

    messages = build_answer_prompt(
        question=state["accumulated_intent"] or state["question"],
        db_results_str=results_str,
    )

    result = await llm.ainvoke(messages)
    answer = result.content.strip()

    tracer.log("answer_formatter", NodeEvent.END)
    return {
        "answer": answer,
        "status": "done",
    }
