"""
FastAPI dependency functions for request-scoped resource injection.

All heavy resources (connector, LLM, graph) are created once during the
application lifespan and stored in ``app.state``.  These thin functions
extract them per-request so route handlers can declare them via ``Depends``.

Usage::

    from api.dependencies import get_connector, get_graph
    from fastapi import Depends

    @router.post("/chat")
    async def chat(graph=Depends(get_graph), connector=Depends(get_connector)):
        ...

Settings used:
    None — resources are already resolved at startup and live in ``app.state``.
"""

from fastapi import Request

from db.base import DatabaseConnector


def get_connector(request: Request) -> DatabaseConnector:
    """
    Return the shared database connector stored in ``app.state``.

    Args:
        request: The current FastAPI request.

    Returns:
        The ``DatabaseConnector`` instance initialised at startup.
    """
    return request.app.state.connector


def get_schema_context(request: Request) -> str:
    """
    Return the cached schema context string stored in ``app.state``.

    The schema is refreshed in the background every 5 minutes; the value
    here is whatever was most recently loaded.

    Args:
        request: The current FastAPI request.

    Returns:
        A prompt-ready schema string describing the university database.
    """
    return request.app.state.schema_context


def get_llm(request: Request):
    """
    Return the LangChain LLM instance stored in ``app.state``.

    Args:
        request: The current FastAPI request.

    Returns:
        The ``ChatAnthropic`` (or compatible) LLM used by all agent nodes.
    """
    return request.app.state.llm


def get_few_shot_examples(request: Request) -> str:
    """
    Return the few-shot SQL examples string stored in ``app.state``.

    Args:
        request: The current FastAPI request.

    Returns:
        Raw SQL few-shot examples loaded from disk at startup.
    """
    return request.app.state.few_shot_examples


def get_graph(request: Request):
    """
    Return the compiled LangGraph graph stored in ``app.state``.

    Args:
        request: The current FastAPI request.

    Returns:
        The compiled ``CompiledGraph`` ready for ``ainvoke``.
    """
    return request.app.state.graph
