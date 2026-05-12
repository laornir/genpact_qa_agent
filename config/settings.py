"""
Application-wide configuration loaded from environment variables / .env file.

All tunables for the agent, database, and external services are declared here.
Import the singleton ``settings`` instance — do not instantiate Settings directly.

Usage::

    from config.settings import settings
    dsn = settings.postgres_dsn

Relevant env vars (see .env.example for full list):
    DB_DRIVER                  -- "postgres" | "sqlite"  (default: "postgres")
    POSTGRES_*                 -- host, port, user, password, db name
    ANTHROPIC_API_KEY          -- required for LLM calls
    LANGCHAIN_*                -- LangSmith tracing (optional)
    MAX_CLARIFICATION_ROUNDS   -- agent loop limit (default: 3)
    MAX_SQL_RETRIES            -- SQL retry limit (default: 2)
    CONVERSATION_HISTORY_WINDOW -- turns kept in prompt (default: 6)
    DB_RESULTS_ROW_LIMIT       -- max rows sent to answer_formatter (default: 50)
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Pydantic-settings model that reads from the .env file and environment.

    Fields are grouped by concern: database, LLM, LangSmith, and agent config.
    Unknown environment variables are silently ignored (``extra="ignore"``).
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_driver: str = "postgres"

    # Postgres
    postgres_user: str = "university"
    postgres_password: str = "university"
    postgres_db: str = "university"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # SQLite (tests only)
    sqlite_path: str = ":memory:"

    # LLM
    anthropic_api_key: str = ""

    # LangSmith
    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "university-qa-agent"

    # Agent config
    log_level: str = "INFO"
    max_clarification_rounds: int = 3
    max_sql_retries: int = 2
    conversation_history_window: int = 6
    db_results_row_limit: int = 50

    @property
    def postgres_dsn(self) -> str:
        """
        Build a PostgreSQL connection string from the individual host/port/auth fields.

        Returns:
            A ``postgresql://user:password@host:port/db`` DSN string
            suitable for asyncpg.
        """
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
