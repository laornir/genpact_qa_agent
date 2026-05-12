"""
Prompt builder for the sql_generator node.

Constructs a system prompt containing the schema and few-shot examples, and
a human message containing the conversation history, the user's intent, and
— on retry turns — the previous failed SQL plus the database error.

Usage::

    from agent.prompts.sql_generator import build_sql_prompt

Settings used:
    None — all inputs are passed explicitly by the calling node.
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from agent.prompts.helpers import format_history

_SYSTEM_TEMPLATE = """\
You are a SQL expert for a university database system.
Generate a single correct SQL SELECT query to answer the user's question.

Database schema:
{schema_context}

Rules:
- Output ONLY the raw SQL query — no markdown, no explanation, no apology
- Do not include a trailing semicolon
- If the request would require modifying data, output a SELECT query
  that retrieves the relevant data instead
- Use only SELECT statements; never output UPDATE, INSERT, DELETE, or any other DML
- Reference only the tables and columns listed in the schema above
- Use table aliases consistently (s for students, t for teachers, c for courses, etc.)

Examples:
{few_shot_examples}\
"""


def build_sql_prompt(
    schema_context: str,
    few_shot_examples: str,
    conversation_history: list[dict],
    accumulated_intent: str,
    retry_sql: str | None = None,
    retry_error: str | None = None,
) -> list[BaseMessage]:
    """
    Build the SQL-generation prompt for the sql_generator node.

    On first attempt (``retry_sql`` and ``retry_error`` are both None) the
    human message contains only the conversation context and the question.
    On retry turns both are provided and a "Previous attempt failed" block is
    appended so the LLM can correct its mistake.

    Args:
        schema_context:       Prompt-ready schema string from ``schema_loader``.
        few_shot_examples:    Contents of the driver-specific ``.sql`` examples
                              file, loaded by ``load_few_shot_examples``.
        conversation_history: Recent turns as ``[{"role", "content"}, ...]``,
                              used for pronoun/reference resolution.
        accumulated_intent:   The merged, unambiguous description of what the
                              user wants (from question_analyzer).
        retry_sql:            The SQL from the previous failed attempt, or None.
        retry_error:          The DB error message from that failure, or None.

    Returns:
        A two-message list ``[SystemMessage, HumanMessage]`` ready for
        ``llm.invoke()``.
    """
    system = _SYSTEM_TEMPLATE.format(
        schema_context=schema_context,
        few_shot_examples=few_shot_examples,
    )

    parts: list[str] = []

    if conversation_history:
        parts.append("Conversation context:\n" + format_history(conversation_history))

    parts.append(f"Question: {accumulated_intent}")

    if retry_sql is not None and retry_error is not None:
        parts.append(
            f"Previous attempt failed:\n"
            f"SQL: {retry_sql}\n"
            f"Error: {retry_error}\n\n"
            "Please generate a corrected SQL query."
        )

    return [SystemMessage(content=system), HumanMessage(content="\n\n".join(parts))]
