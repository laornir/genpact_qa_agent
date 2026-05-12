"""
SQL-executor node — runs the validated SQL against the database connector.

On success it advances status to ``"formatting"`` and stores the result rows.
On failure it either schedules a retry (status → ``"generating"``) or
terminates with an error if the retry limit is exhausted.

The database connector is injected via ``config["configurable"]["connector"]``
so the node is testable with any ``DatabaseConnector`` implementation.

Usage::

    from agent.nodes.sql_executor import sql_executor

Settings used (via ``config["configurable"]``):
    connector       -- DatabaseConnector instance
    max_sql_retries -- int, default 2 (allows 2 retries after the first attempt)
"""

from langchain_core.runnables import RunnableConfig

from agent.state import AgentState
from agent.tracing import NodeEvent


async def sql_executor(state: AgentState, config: RunnableConfig) -> dict:
    """
    LangGraph node (async): execute the SQL query and handle DB errors.

    Increments ``retry_count`` and routes back to ``sql_generator`` on failure
    when retries remain.  Routes to ``"error"`` when the retry limit is
    exhausted.

    Args:
        state:  Current AgentState; reads ``sql``, ``retry_count``, and ``tracer``.
        config: LangGraph RunnableConfig; must contain
                ``config["configurable"]["connector"]`` and optionally
                ``config["configurable"]["max_sql_retries"]``.

    Returns:
        Partial state dict with ``status`` and either ``db_results`` (success)
        or ``sql_error`` + ``retry_count`` (failure).
    """
    tracer = state["tracer"]
    tracer.log("sql_executor", NodeEvent.START)

    connector = config["configurable"]["connector"]
    max_retries: int = config["configurable"].get("max_sql_retries", 2)

    try:
        results: list[dict] = await connector.execute_query(state["sql"] or "")
        tracer.log("sql_executor", NodeEvent.END, row_count=len(results))
        return {
            "db_results": results,
            "status": "formatting",
            "sql_error": None,
        }
    except Exception as exc:
        error_msg = str(exc)
        new_retry_count = state["retry_count"] + 1

        if new_retry_count <= max_retries:
            tracer.log(
                "sql_executor",
                NodeEvent.RETRY,
                retry_count=new_retry_count,
                error=error_msg,
            )
            return {
                "sql_error": error_msg,
                "retry_count": new_retry_count,
                "status": "generating",
            }

        tracer.log("sql_executor", NodeEvent.ERROR, reason=error_msg)
        return {
            "sql_error": error_msg,
            "status": "error",
            "answer": "Failed to execute the query after multiple attempts.",
        }
