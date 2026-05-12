"""
FastAPI application entry point for the university QA agent.

Initialises all shared resources during the lifespan (database connector,
schema context, few-shot SQL examples, LLM, compiled graph) and starts a
background task that refreshes the schema context every 5 minutes to pick
up any DDL changes without a full restart.

Usage::

    uvicorn api.main:app --host 0.0.0.0 --port 8000

Settings used:
    DB_DRIVER, POSTGRES_*, SQLITE_PATH, ANTHROPIC_API_KEY,
    LANGCHAIN_*, LOG_LEVEL (all read from ``config.settings``).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from langchain_anthropic import ChatAnthropic

from agent.graph import build_graph
from agent.prompts.sql_examples import load_few_shot_examples
from agent.tracing import setup_logging
from api.routes import router
from config.settings import settings
from db.factory import get_connector as _get_connector
from db.schema_loader import load_schema_context

_logger = logging.getLogger(__name__)

_SCHEMA_REFRESH_SECONDS = 300  # 5 minutes


async def _refresh_schema_loop(app: FastAPI, connector) -> None:
    """
    Background coroutine that refreshes ``app.state.schema_context`` every 5 minutes.

    Runs until cancelled at shutdown.  On failure the previous schema is
    retained so in-flight requests are not affected.

    Args:
        app: The FastAPI application whose ``state.schema_context`` to update.
        connector: The database connector used to re-fetch the schema.
    """
    while True:
        await asyncio.sleep(_SCHEMA_REFRESH_SECONDS)
        try:
            app.state.schema_context = await load_schema_context(connector)
            _logger.info("Schema context refreshed")
        except Exception:
            _logger.exception("Schema refresh failed; retaining previous context")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    FastAPI lifespan that initialises and tears down shared resources.

    Startup order:
        1. Structured logging
        2. Database connector
        3. Schema context (initial load from DB)
        4. Few-shot SQL examples (loaded from disk)
        5. LLM (``ChatAnthropic``)
        6. Compiled LangGraph graph
        7. Background schema-refresh task

    Shutdown cancels the refresh task and closes the database connection.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control to the running application after all resources are ready.
    """
    setup_logging(settings.log_level)
    _logger.info("Starting university QA agent")

    connector = _get_connector()
    app.state.connector = connector
    _logger.info("Database connector created (driver=%s)", settings.db_driver)

    app.state.schema_context = await load_schema_context(connector)
    _logger.info("Schema context loaded")

    app.state.few_shot_examples = load_few_shot_examples(settings.db_driver)
    _logger.info("Few-shot examples loaded (driver=%s)", settings.db_driver)

    app.state.llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        api_key=settings.anthropic_api_key or None,
    )
    _logger.info("LLM initialised (model=claude-sonnet-4-6)")

    app.state.graph = build_graph()
    _logger.info("LangGraph graph compiled")

    refresh_task = asyncio.create_task(
        _refresh_schema_loop(app, connector),
        name="schema-refresh",
    )

    yield

    refresh_task.cancel()
    with suppress(asyncio.CancelledError):
        await refresh_task
    await connector.close()
    _logger.info("University QA agent stopped")


app = FastAPI(
    title="University QA Agent",
    description="Natural-language Q&A over a university database.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)
