"""
SQL-generator node — produces a SQL SELECT query from the accumulated intent.

On first attempt the prompt contains only the schema, few-shot examples,
conversation history, and the user's question. On retry turns (when
``state["retry_count"] > 0``) a "Previous attempt failed" block is appended
so the LLM can correct its mistake.

The generated SQL is written back to ``state["sql"]``; the node sets status
to ``"validating"`` so the graph routes next to ``sql_validator``.

Usage::

    from agent.nodes.sql_generator import sql_generator

Settings used (via ``config["configurable"]``):
    llm               -- LangChain chat model instance
    few_shot_examples -- pre-loaded SQL examples string (from load_few_shot_examples)
"""

from langchain_core.runnables import RunnableConfig

from agent.prompts.sql_generator import build_sql_prompt
from agent.state import AgentState
from agent.tracing import NodeEvent


async def sql_generator(state: AgentState, config: RunnableConfig) -> dict:
    """
    LangGraph node: generate a SQL query for the current intent.

    Includes the previous SQL and error message in the prompt when retrying.
    Always advances status to ``"validating"`` and clears ``sql_error``.

    Args:
        state:  Current AgentState; reads ``accumulated_intent``, ``schema_context``,
                ``conversation_history``, ``retry_count``, ``sql``, and ``sql_error``.
        config: LangGraph RunnableConfig; must contain
                ``config["configurable"]["llm"]`` and
                ``config["configurable"]["few_shot_examples"]``.

    Returns:
        Partial state dict with ``sql``, ``status``, and ``sql_error``.
    """
    tracer = state["tracer"]
    tracer.log("sql_generator", NodeEvent.START, retry_count=state["retry_count"])

    llm = config["configurable"]["llm"]
    few_shot_examples: str = config["configurable"]["few_shot_examples"]

    retry_count = state["retry_count"]
    messages = build_sql_prompt(
        schema_context=state["schema_context"],
        few_shot_examples=few_shot_examples,
        conversation_history=state["conversation_history"],
        accumulated_intent=state["accumulated_intent"] or state["question"],
        retry_sql=state["sql"] if retry_count > 0 else None,
        retry_error=state["sql_error"] if retry_count > 0 else None,
    )

    result = await llm.ainvoke(messages)
    sql = result.content.strip()

    tracer.log("sql_generator", NodeEvent.END, sql=sql, retry_count=retry_count)
    return {
        "sql": sql,
        "status": "validating",
        "sql_error": None,
    }
