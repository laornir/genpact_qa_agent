"""Tests for agent/prompts/sql_examples/__init__.py — load_few_shot_examples()."""

import pytest

from agent.prompts.sql_examples import load_few_shot_examples


def test_loads_postgres_examples():
    """Postgres examples file loads successfully and contains SELECT statements."""
    examples = load_few_shot_examples("postgres")
    assert "SELECT" in examples


def test_loads_sqlite_examples():
    """SQLite examples file loads successfully and contains SELECT statements."""
    examples = load_few_shot_examples("sqlite")
    assert "SELECT" in examples


def test_postgres_and_sqlite_content_differ():
    """Postgres and SQLite example files have different content."""
    postgres = load_few_shot_examples("postgres")
    sqlite = load_few_shot_examples("sqlite")
    assert postgres != sqlite


def test_unknown_driver_raises_value_error():
    """An unrecognised driver string raises ValueError."""
    with pytest.raises(ValueError, match="oracle"):
        load_few_shot_examples("oracle")
