"""
PostgreSQL adapter built on asyncpg.

Implements ``DatabaseConnector`` for a live PostgreSQL instance.
A connection pool is created lazily on the first query and reused for the
lifetime of the connector — typically the FastAPI application lifetime.

Usage::

    from db.postgres import PostgresConnector
    connector = PostgresConnector(settings.postgres_dsn)
    rows = await connector.execute_query("SELECT * FROM students")
    await connector.close()   # call during app shutdown

Settings used:
    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST,
    POSTGRES_PORT, POSTGRES_DB  →  composed into ``settings.postgres_dsn``
"""

import asyncpg

from .base import DatabaseConnector

_SCHEMA_QUERY = """
    SELECT
        col.table_name,
        col.column_name,
        col.data_type,
        fk.foreign_table AS references_table,
        fk.foreign_column AS references_column
    FROM information_schema.columns col
    LEFT JOIN (
        SELECT
            kcu.table_name,
            kcu.column_name,
            ccu.table_name  AS foreign_table,
            ccu.column_name AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema   = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
            ON tc.constraint_name = ccu.constraint_name
            AND tc.table_schema   = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema    = 'public'
    ) fk ON col.table_name  = fk.table_name
         AND col.column_name = fk.column_name
    WHERE col.table_schema = 'public'
    ORDER BY col.table_name, col.ordinal_position
"""


class PostgresConnector(DatabaseConnector):
    """
    Async PostgreSQL connector backed by an asyncpg connection pool.

    The pool is created on the first call to any query method and is
    shared across all subsequent calls. Call ``close()`` on application
    shutdown to release all pooled connections.
    """

    def __init__(self, dsn: str) -> None:
        """
        Args:
            dsn: A ``postgresql://user:password@host:port/db`` connection string.
        """
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None

    async def _pool_(self) -> asyncpg.Pool:
        """
        Return the connection pool, initialising it on first call.

        Returns:
            A ready asyncpg Pool instance.
        """
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn)
        return self._pool  # type: ignore[return-value]

    async def execute_query(self, sql: str) -> list[dict]:
        """
        Execute a SQL statement and return results as a list of row dicts.

        Args:
            sql: A read-only SQL statement. Should be a SELECT query;
                 write operations are blocked upstream by the SQL validator.

        Returns:
            A list of dicts mapping column name → value, one per row.
            Returns an empty list when the query produces no rows.
        """
        pool = await self._pool_()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)
            return [dict(row) for row in rows]

    async def fetch_schema(self) -> list[dict]:
        """
        Introspect the ``public`` schema via ``information_schema``.

        Joins ``columns``, ``table_constraints``, ``key_column_usage``, and
        ``constraint_column_usage`` to resolve foreign-key targets in a single
        query, avoiding N+1 PRAGMA calls.

        Returns:
            A list of column records:
                - ``table``      (str)       -- table name
                - ``column``     (str)       -- column name
                - ``type``       (str)       -- PostgreSQL data type name
                - ``is_fk``      (bool)      -- True if column is a FK
                - ``references`` (str | None)-- "table.column" target or None
        """
        rows = await self.execute_query(_SCHEMA_QUERY)
        return [
            {
                "table": row["table_name"],
                "column": row["column_name"],
                "type": row["data_type"],
                "is_fk": row["references_table"] is not None,
                "references": (
                    f"{row['references_table']}.{row['references_column']}"
                    if row["references_table"]
                    else None
                ),
            }
            for row in rows
        ]

    async def healthcheck(self) -> bool:
        """
        Confirm the database is reachable by running ``SELECT 1``.

        Returns:
            True on success, False on any connection or query error.
        """
        try:
            return bool(await self.execute_query("SELECT 1"))
        except Exception:
            return False

    async def close(self) -> None:
        """
        Gracefully close the connection pool.

        Safe to call even if the pool was never initialised.
        Should be called during FastAPI lifespan shutdown.
        """
        if self._pool:
            await self._pool.close()
            self._pool = None
