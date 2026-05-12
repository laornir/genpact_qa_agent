"""
Database connector factory.

Reads ``DB_DRIVER`` from settings and returns the matching
``DatabaseConnector`` implementation. This is the only place in the codebase
that decides which adapter to instantiate — all other code depends only on the
``DatabaseConnector`` abstract interface.

Usage::

    from db.factory import get_connector
    connector = get_connector()   # returns Postgres or SQLite based on env

Settings used:
    DB_DRIVER    -- "postgres" | "sqlite"  (default: "postgres")
    POSTGRES_*   -- used when DB_DRIVER="postgres"
    SQLITE_PATH  -- used when DB_DRIVER="sqlite"  (default: ":memory:")
"""

from .base import DatabaseConnector
from .postgres import PostgresConnector
from .sqlite import SQLiteConnector


def get_connector() -> DatabaseConnector:
    """
    Instantiate and return the database connector for the current environment.

    The connector is constructed but not yet connected — the underlying pool
    or connection is opened lazily on the first query.

    Returns:
        A ``PostgresConnector`` when ``DB_DRIVER=postgres``,
        or a ``SQLiteConnector`` when ``DB_DRIVER=sqlite``.

    Raises:
        ValueError: If ``DB_DRIVER`` is set to an unrecognised value.
    """
    from config.settings import settings

    match settings.db_driver:
        case "postgres":
            return PostgresConnector(settings.postgres_dsn)
        case "sqlite":
            return SQLiteConnector(settings.sqlite_path)
        case _:
            raise ValueError(f"Unknown DB_DRIVER: {settings.db_driver!r}")
