"""
Prompt builders for the question_analyzer node.

Two prompts are used in sequence (merger only when resuming clarification):

1. **Merger prompt** — merges the user's new input with the previous
   accumulated intent into a single plain-text description. Called only when
   ``last_clarification`` is set (i.e. the agent asked a clarifying question
   in the previous turn).

2. **Classifier prompt** — classifies the (possibly merged) intent as
   ``answerable``, ``ambiguous``, or ``out_of_scope``. Returns strict JSON so
   the node can route without further parsing heuristics.

Usage::

    from agent.prompts.question_analyzer import build_merger_prompt, build_classifier_prompt

Settings used:
    None — all inputs are passed explicitly by the calling node.
"""

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

_MERGER_SYSTEM = """\
You are tracking a user's intent across a multi-turn university Q&A session.
The user was asked a clarification question and has now responded.
Merge the previous intent with the user's new response into a single, clear
plain-text description of what the user wants to know.

Output ONLY the merged intent — no explanation, no JSON, no punctuation wrapper.\
"""

_CLASSIFIER_SYSTEM_TEMPLATE = """\
You are classifying a user's question for a university database Q&A system.

Database schema:
{schema_context}

Classify the user's intent as exactly one of:
  "answerable"   — can be answered with a SQL query against the schema above
  "ambiguous"    — needs clarification before SQL can be written
  "out_of_scope" — cannot be answered from this database

Respond with ONLY valid JSON in this exact format (no markdown, no extra keys):
{{"status": "answerable"|"ambiguous"|"out_of_scope",
  "clarification_question": "<question to ask the user, or empty string>",
  "reason": "<brief internal note, never shown to the user>"}}
"""


def build_merger_prompt(
    accumulated_intent: str | None,
    last_clarification: str,
    current_input: str,
) -> list[BaseMessage]:
    """
    Build the intent-merger prompt for the question_analyzer node.

    Called only when ``last_clarification`` is not None (i.e. we are resuming
    a clarification turn). The LLM returns a plain string that overwrites
    ``accumulated_intent`` in the agent state.

    Args:
        accumulated_intent: The intent description built up in previous turns,
                            or None if this is the very first clarification round.
        last_clarification: The clarification question the agent asked last turn.
        current_input:      The user's answer to that clarification question.

    Returns:
        A two-message list ``[SystemMessage, HumanMessage]`` ready for
        ``llm.invoke()``.
    """
    human = (
        f"Previous intent: {accumulated_intent or '(none yet)'}\n"
        f"Clarification question asked: {last_clarification}\n"
        f"User's response: {current_input}\n\n"
        "Merged intent:"
    )
    return [SystemMessage(content=_MERGER_SYSTEM), HumanMessage(content=human)]


def build_classifier_prompt(
    accumulated_intent: str,
    schema_context: str,
) -> list[BaseMessage]:
    """
    Build the intent-classifier prompt for the question_analyzer node.

    Always called (after the optional merger step). The LLM must return
    valid JSON with ``status``, ``clarification_question``, and ``reason``.

    Args:
        accumulated_intent: The current (possibly merged) description of what
                            the user wants to know.
        schema_context:     The prompt-ready schema string from
                            ``db/schema_loader.py``, injected so the LLM can
                            judge whether the question is answerable.

    Returns:
        A two-message list ``[SystemMessage, HumanMessage]`` ready for
        ``llm.invoke()``.
    """
    system = _CLASSIFIER_SYSTEM_TEMPLATE.format(schema_context=schema_context)
    human = f"User intent: {accumulated_intent}"
    return [SystemMessage(content=system), HumanMessage(content=human)]
