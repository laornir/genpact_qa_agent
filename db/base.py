"""
Abstract database connector interface.

Defines the contract that every database adapter must fulfill.
Concrete implementations live in ``db/postgres.py`` and ``db/sqlite.py``.
The factory in ``db/factory.py`` selects the right implementation at runtime
based on the ``DB_DRIVER`` setting.

All methods are async to support non-blocking I/O across adapters.
"""

from abc import ABC, abstractmethod


class DatabaseConnector(ABC):
    """Common interface for all database backends used by the agent."""

    @abstractmethod
    async def execute_query(self, sql: str) -> list[dict]:
        """
        Run a SQL query and return the results as a list of row dicts.

        Args:
            sql: A read-only SQL statement (SELECT). The SQL validator node
                 ensures only safe queries reach this method.

        Returns:
            A list of dicts mapping column name → value, one dict per row.
            Returns an empty list when the query produces no rows.
        """
        ...

    @abstractmethod
    async def fetch_schema(self) -> list[dict]:
        """
        Introspect the database and return one record per column.

        Returns:
            A list of dicts with the following keys:
                - ``table``      (str)       -- table name
                - ``column``     (str)       -- column name
                - ``type``       (str)       -- data type as reported by the DB
                - ``is_fk``      (bool)      -- True if this column is a foreign key
                - ``references`` (str | None)-- "referenced_table.column" or None
        """
        ...

    @abstractmethod
    async def healthcheck(self) -> bool:
        """
        Verify that the database is reachable and accepting queries.

        Returns:
            True if a trivial query succeeds, False on any connection error.
        """
        ...
