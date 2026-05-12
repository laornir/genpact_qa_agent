"""
Database schema formatter for LLM prompt injection.

Calls ``connector.fetch_schema()`` and converts the raw column records into a
compact, human-readable string that is embedded in SQL-generation prompts.
FK columns are rendered with arrow notation (``col→table.id``) so the LLM
understands join paths without reading the full DDL.

The schema context is loaded once at FastAPI startup and cached; nodes never
call this directly — they receive the pre-built string via ``AgentState``.

Usage::

    from db.schema_loader import load_schema_context
    ctx = await load_schema_context(connector)
    # "teachers: id, name, email\\nstudents: id, name, email, enrollment_year\\n..."

Settings used:
    None — formatting is deterministic given the connector output.
"""

from .base import DatabaseConnector


async def load_schema_context(connector: DatabaseConnector) -> str:
    """
    Build a prompt-ready schema string from the connector's introspection data.

    Each table is rendered as a single line::

        table_name: col1, col2, fk_col→referenced_table.id, ...

    Tables appear in the order returned by ``fetch_schema`` (alphabetical for
    both adapters). Columns preserve declaration order.

    Args:
        connector: Any ``DatabaseConnector`` implementation. Called once via
                   ``fetch_schema()``; results are not cached here.

    Returns:
        A newline-separated string with one line per table, ready to be
        injected into the SQL-generation prompt as schema context.
    """
    rows = await connector.fetch_schema()

    tables: dict[str, list[str]] = {}
    for row in rows:
        table = row["table"]
        if table not in tables:
            tables[table] = []

        col = row["column"]
        if row["is_fk"] and row["references"]:
            col = f"{col}→{row['references']}"
        tables[table].append(col)

    return "\n".join(f"{table}: {', '.join(cols)}" for table, cols in tables.items())
