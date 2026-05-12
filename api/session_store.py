"""
In-memory conversation history store.

Holds per-session state that must survive between API calls: the last graph
status, clarification tracking fields, and conversation turns.  Production
replacement: Redis with JSON serialisation of ``ConversationHistory``.

Usage::

    from api.session_store import session_store
    history = session_store.get(session_id)
    session_store.save(session_id, history)

Settings used:
    None — pure in-memory, no external configuration required.
"""

from dataclasses import dataclass, field


@dataclass
class ConversationHistory:
    """
    Per-session state bridging successive HTTP requests.

    The API layer reads ``last_status`` to decide whether the incoming
    question is a fresh start or a clarification continuation.  The three
    clarification fields are only carried forward when
    ``last_status == "asking_clarification"``; otherwise they are reset to
    their defaults before the graph runs.

    ``turns`` grows unbounded in this in-memory implementation; a production
    store would cap it or offload old turns to cold storage.
    """

    last_status: str = "done"
    """Status returned by the most recent graph run for this session."""

    last_clarification_question: str | None = None
    """Clarification question the agent asked in the previous turn, if any."""

    accumulated_intent: str | None = None
    """Merged user intent built up across clarification rounds."""

    ambiguity_count: int = 0
    """Number of clarification rounds elapsed for the current question."""

    turns: list[dict] = field(default_factory=list)
    """All conversation turns as ``[{"role": "user"|"assistant", "content": "..."}, ...]``."""


class SessionStore:
    """
    Thread-safe in-memory mapping of ``session_id`` to ``ConversationHistory``.

    Safe for a single asyncio event loop; the GIL protects plain dict
    reads and writes within one process.  Replace with a Redis-backed
    implementation for multi-process or multi-node deployments.
    """

    def __init__(self) -> None:
        """Initialise an empty store."""
        self._store: dict[str, ConversationHistory] = {}

    def get(self, session_id: str) -> ConversationHistory:
        """
        Return the history for a session, creating a blank one if absent.

        Args:
            session_id: Client-provided stable conversation identifier.

        Returns:
            The stored ``ConversationHistory``, or a fresh default instance.
        """
        return self._store.get(session_id, ConversationHistory())

    def save(self, session_id: str, history: ConversationHistory) -> None:
        """
        Persist an updated history for a session.

        Args:
            session_id: Client-provided stable conversation identifier.
            history: The updated ``ConversationHistory`` to store.
        """
        self._store[session_id] = history


session_store = SessionStore()
