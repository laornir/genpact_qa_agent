"""
E2E test fixtures wiring a real SQLite connector with a mock LLM.

``test_app`` builds a minimal FastAPI instance (no lifespan) with
``app.state`` pre-populated from the seeded SQLite database.  Each test
sets ``test_app.state.llm`` to a ``MagicMock`` configured with the LLM
responses needed for that scenario.

``client`` exposes an ``httpx.AsyncClient`` pointed at ``test_app``.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from agent.graph import build_graph
from agent.prompts.sql_examples import load_few_shot_examples
from api.routes import router
from db.schema_loader import load_schema_context


@pytest.fixture
async def test_app(seeded_connector):
    """
    Return a minimal FastAPI app with seeded SQLite state but no LLM set.

    Tests must assign ``test_app.state.llm`` before making requests so the
    graph nodes receive a properly configured mock.
    """
    schema_context = await load_schema_context(seeded_connector)

    app = FastAPI()
    app.state.connector = seeded_connector
    app.state.schema_context = schema_context
    app.state.few_shot_examples = load_few_shot_examples("sqlite")
    app.state.graph = build_graph()
    app.include_router(router)
    return app


@pytest.fixture
async def client(test_app):
    """
    Yield an AsyncClient pointed at the test FastAPI app.

    Use alongside ``test_app`` to set ``test_app.state.llm`` before
    issuing requests.
    """
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
        yield ac
