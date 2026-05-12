"""
Prompt builder for the answer_formatter node.

Takes the original user question and the JSON-serialised query results and
instructs the LLM to produce a natural-language answer. The LLM is explicitly
told not to mention SQL, databases, or query mechanics.

Usage::

    from agent.prompts.answer_formatter import build_answer_prompt

Settings used:
    None — result truncation is applied by the node before calling this builder.
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_SYSTEM = """\
You are answering a user's question about a university.
You have been given the raw results of a database query.
Produce a clear, concise, natural-language answer.

Rules:
- Write in plain English; never mention SQL, databases, or queries
- Empty results: state that no matching information was found
- Single scalar value: state it directly in one sentence
- List of fewer than 5 items: write them in flowing prose
- List of 5 or more items: use a bulleted list
- Do not invent information that is not in the query results\
"""


def build_answer_prompt(question: str, db_results_str: str) -> list[BaseMessage]:
    """
    Build the answer-formatting prompt for the answer_formatter node.

    Args:
        question:        The original user question (used to frame the answer).
        db_results_str:  JSON string of query result rows, already truncated to
                         the configured row limit by the calling node.

    Returns:
        A two-message list ``[SystemMessage, HumanMessage]`` ready for
        ``llm.invoke()``.
    """
    human = f"Question: {question}\n\nQuery results (JSON):\n{db_results_str}\n\nAnswer:"
    return [SystemMessage(content=_SYSTEM), HumanMessage(content=human)]
