"""
SQLite adapter built on aiosqlite.

Intended exclusively for unit and integration tests — never used in production.
A single persistent connection is kept open for the lifetime of the connector,
which is required for ``:memory:`` databases (each new connection would be a
separate, empty database).

Foreign-key enforcement is enabled on connect via ``PRAGMA foreign_keys = ON``
so that FK constraint violations are raised during tests exactly as they would
be on PostgreSQL.

Usage::

    from db.sqlite import SQLiteConnector
    connector = SQLiteConnector(":memory:")
    rows = await connector.execute_query("SELECT * FROM students")
    await connector.close()

Settings used:
    SQLITE_PATH  -- filesystem path or ``:memory:`` (default: ``:memory:``)
"""

import aiosqlite

from .base import DatabaseConnector


class SQLiteConnector(DatabaseConnector):
    """
    Async SQLite connector backed by a single aiosqlite connection.

    Schema introspection uses SQLite's ``PRAGMA table_info`` and
    ``PRAGMA foreign_key_list`` rather than ``information_schema``,
    producing the same output schema as ``PostgresConnector.fetch_schema``.
    """

    def __init__(self, path: str = ":memory:") -> None:
        """
        Args:
            path: Filesystem path to the SQLite database file,
                  or ``:memory:`` for a transient in-memory database.
        """
        self._path = path
        self._conn: aiosqlite.Connection | None = None

    async def _get_conn(self) -> aiosqlite.Connection:
        """
        Return the underlying connection, opening it on first call.

        Also enables foreign-key enforcement for the session so that
        constraint violations surface during tests.

        Returns:
            An open aiosqlite Connection instance.
        """
        if self._conn is None:
            self._conn = await aiosqlite.connect(self._path)
            await self._conn.execute("PRAGMA foreign_keys = ON")
        return self._conn

    async def execute_query(self, sql: str) -> list[dict]:
        """
        Execute a SQL statement and return results as a list of row dicts.

        Args:
            sql: Any valid SQLite statement. For SELECT queries the results
                 are returned; for DDL/DML an empty list is returned.

        Returns:
            A list of dicts mapping column name → value, one per row.
            Returns an empty list when the query produces no rows.
        """
        conn = await self._get_conn()
        async with conn.execute(sql) as cursor:
            rows = await cursor.fetchall()
            if not rows:
                return []
            cols = [desc[0] for desc in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

    async def fetch_schema(self) -> list[dict]:
        """
        Introspect all user tables via SQLite PRAGMA statements.

        For each table, runs ``PRAGMA foreign_key_list`` to build a FK map,
        then ``PRAGMA table_info`` to enumerate columns, annotating each
        column with its FK target when present.

        Returns:
            A list of column records (same shape as PostgresConnector):
                - ``table``      (str)       -- table name
                - ``column``     (str)       -- column name
                - ``type``       (str)       -- declared column type
                - ``is_fk``      (bool)      -- True if column is a FK
                - ``references`` (str | None)-- "table.column" target or None
        """
        conn = await self._get_conn()

        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ) as cursor:
            tables = [row[0] for row in await cursor.fetchall()]

        result: list[dict] = []
        for table in tables:
            fk_map: dict[str, str] = {}
            async with conn.execute(f"PRAGMA foreign_key_list({table})") as cursor:
                for row in await cursor.fetchall():
                    # row: (id, seq, referenced_table, from_col, to_col, ...)
                    fk_map[row[3]] = f"{row[2]}.{row[4]}"

            async with conn.execute(f"PRAGMA table_info({table})") as cursor:
                for row in await cursor.fetchall():
                    # row: (cid, name, type, notnull, dflt_value, pk)
                    col_name = row[1]
                    references = fk_map.get(col_name)
                    result.append(
                        {
                            "table": table,
                            "column": col_name,
                            "type": row[2],
                            "is_fk": col_name in fk_map,
                            "references": references,
                        }
                    )

        return result

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
        Close the underlying connection and reset internal state.

        Safe to call even if the connection was never opened.
        """
        if self._conn:
            await self._conn.close()
            self._conn = None
