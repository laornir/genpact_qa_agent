"""
Shared prompt-formatting utilities used across multiple prompt builders.

These functions convert Python objects into strings suitable for embedding
in LLM prompt messages. They enforce the output row limit and keep
formatting consistent across all prompt types.

Usage::

    from agent.prompts.helpers import format_history, format_db_results, truncate_results

Settings used:
    DB_RESULTS_ROW_LIMIT -- enforced via ``truncate_results``; callers pass
                            the value from settings rather than reading it here.
"""

import json


def format_history(conversation_history: list[dict]) -> str:
    """
    Format conversation turns into a readable multi-line string.

    Each turn is rendered as ``Role: content`` on its own line.
    Intended for injection into the sql_generator prompt to give the LLM
    reference-resolution context ("that course" → "Algorithms").

    Args:
        conversation_history: List of ``{"role": str, "content": str}`` dicts,
                               ordered oldest-first.

    Returns:
        A newline-separated string of ``Role: content`` lines,
        or an empty string when the list is empty.
    """
    return "\n".join(
        f"{turn['role'].capitalize()}: {turn['content']}" for turn in conversation_history
    )


def format_db_results(db_results: list[dict]) -> str:
    """
    Serialise query result rows to a compact JSON string.

    Non-JSON-serialisable values (e.g. ``datetime``) are coerced to strings
    via ``default=str`` so the formatter never raises on real DB output.

    Args:
        db_results: List of row dicts as returned by ``DatabaseConnector.execute_query``.

    Returns:
        A JSON array string, e.g. ``[{"name": "Alice"}, ...]``.
        Returns ``"[]"`` for an empty list.
    """
    return json.dumps(db_results, indent=2, default=str)


def truncate_results(db_results: list[dict], row_limit: int) -> list[dict]:
    """
    Clip the result list to at most ``row_limit`` rows.

    Prevents oversized result sets from blowing up the answer_formatter's
    context window. The limit is read from ``settings.db_results_row_limit``
    and passed in by the caller.

    Args:
        db_results: Full list of row dicts from the database.
        row_limit:  Maximum number of rows to keep.

    Returns:
        The first ``row_limit`` rows, or the full list if it is shorter.
    """
    return db_results[:row_limit]
