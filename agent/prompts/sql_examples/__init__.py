"""
Few-shot SQL example loader for the sql_generator prompt.

Reads a driver-specific ``.sql`` file from this package directory and returns
its content as a single string. The loader is called once at application
startup; the result is cached and injected into every ``build_sql_prompt``
call via the graph's ``config["configurable"]["few_shot_examples"]``.

Usage::

    from agent.prompts.sql_examples import load_few_shot_examples
    examples = load_few_shot_examples("postgres")

Settings used:
    DB_DRIVER -- determines which file is loaded; passed as the ``driver``
                 argument rather than read directly here.
"""

from pathlib import Path

_DIR = Path(__file__).parent


def load_few_shot_examples(driver: str) -> str:
    """
    Load the SQL few-shot examples file for the given database driver.

    Args:
        driver: One of ``"postgres"`` or ``"sqlite"``.

    Returns:
        The full contents of the matching ``.sql`` file as a string.

    Raises:
        ValueError: If ``driver`` is not one of the supported values.
    """
    match driver:
        case "postgres":
            filename = "postgres_examples.sql"
        case "sqlite":
            filename = "sqlite_examples.sql"
        case _:
            raise ValueError(f"No SQL examples for driver: {driver!r}")

    return (_DIR / filename).read_text()
