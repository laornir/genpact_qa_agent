"""Tests for agent/tracing.py — NodeEvent enum, Tracer.log(), and setup_logging()."""

import json
import logging

from agent.tracing import NodeEvent, Tracer, setup_logging

# ---------------------------------------------------------------------------
# NodeEvent
# ---------------------------------------------------------------------------


def test_node_event_values():
    """NodeEvent defines all six expected lifecycle event strings."""
    assert NodeEvent.START == "start"
    assert NodeEvent.END == "end"
    assert NodeEvent.ERROR == "error"
    assert NodeEvent.RETRY == "retry"
    assert NodeEvent.CLARIFY == "clarification_requested"
    assert NodeEvent.SKIP == "skip"


def test_node_event_is_str():
    """NodeEvent members are plain str instances for JSON serialisation compatibility."""
    for event in NodeEvent:
        assert isinstance(event, str)


# ---------------------------------------------------------------------------
# Tracer.log — JSON structure
# ---------------------------------------------------------------------------


def test_log_emits_one_record(caplog):
    """A single log() call produces exactly one log record."""
    tracer = Tracer(trace_id="t1", session_id="s1")
    with caplog.at_level(logging.INFO, logger="university_qa"):
        tracer.log("sql_generator", NodeEvent.END)
    assert len(caplog.records) == 1


def test_log_record_is_valid_json(caplog):
    """The emitted log message is a parseable JSON object."""
    tracer = Tracer(trace_id="t1", session_id="s1")
    with caplog.at_level(logging.INFO, logger="university_qa"):
        tracer.log("sql_generator", NodeEvent.END)
    json.loads(caplog.messages[0])  # raises if invalid


def test_log_contains_required_fields(caplog):
    """Every log line contains ts, trace_id, session_id, node, and event."""
    tracer = Tracer(trace_id="abc", session_id="xyz")
    with caplog.at_level(logging.INFO, logger="university_qa"):
        tracer.log("question_analyzer", NodeEvent.START)
    record = json.loads(caplog.messages[0])
    assert record["trace_id"] == "abc"
    assert record["session_id"] == "xyz"
    assert record["node"] == "question_analyzer"
    assert record["event"] == "start"
    assert "ts" in record


def test_log_event_value_is_string(caplog):
    """The 'event' field is serialised as a plain string, not an enum repr."""
    tracer = Tracer(trace_id="t1", session_id="s1")
    with caplog.at_level(logging.INFO, logger="university_qa"):
        tracer.log("sql_executor", NodeEvent.RETRY)
    record = json.loads(caplog.messages[0])
    assert record["event"] == "retry"
    assert record["event"] != "NodeEvent.RETRY"


def test_log_kwargs_included_in_record(caplog):
    """Extra keyword arguments are merged into the JSON record as top-level fields."""
    tracer = Tracer(trace_id="t1", session_id="s1")
    with caplog.at_level(logging.INFO, logger="university_qa"):
        tracer.log("sql_generator", NodeEvent.END, sql="SELECT 1", retry_count=1)
    record = json.loads(caplog.messages[0])
    assert record["sql"] == "SELECT 1"
    assert record["retry_count"] == 1


def test_log_no_kwargs_omits_extra_fields(caplog):
    """A log() call with no kwargs produces a record with exactly the five base fields."""
    tracer = Tracer(trace_id="t1", session_id="s1")
    with caplog.at_level(logging.INFO, logger="university_qa"):
        tracer.log("answer_formatter", NodeEvent.END)
    record = json.loads(caplog.messages[0])
    assert set(record.keys()) == {"ts", "trace_id", "session_id", "node", "event"}


def test_log_different_events_produce_separate_records(caplog):
    """Multiple log() calls each produce an independent record in order."""
    tracer = Tracer(trace_id="t1", session_id="s1")
    with caplog.at_level(logging.INFO, logger="university_qa"):
        tracer.log("sql_executor", NodeEvent.START)
        tracer.log("sql_executor", NodeEvent.ERROR, error="timeout")
    assert len(caplog.messages) == 2
    first = json.loads(caplog.messages[0])
    second = json.loads(caplog.messages[1])
    assert first["event"] == "start"
    assert second["event"] == "error"
    assert second["error"] == "timeout"


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------


def test_setup_logging_sets_level():
    """setup_logging configures the university_qa logger to the requested level."""
    setup_logging("DEBUG")
    assert logging.getLogger("university_qa").level == logging.DEBUG
    setup_logging("INFO")  # restore


def test_setup_logging_does_not_duplicate_handlers():
    """Calling setup_logging twice does not add a second handler."""
    setup_logging("INFO")
    before = len(logging.getLogger("university_qa").handlers)
    setup_logging("INFO")
    after = len(logging.getLogger("university_qa").handlers)
    assert after == before
