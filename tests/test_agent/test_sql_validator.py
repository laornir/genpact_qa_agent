"""Tests for agent/nodes/sql_validator.py — validate_sql() and the sql_validator node."""

from agent.nodes.sql_validator import sql_validator, validate_sql
from tests.test_agent.conftest import make_state

# ---------------------------------------------------------------------------
# validate_sql — SELECT / WITH whitelist
# ---------------------------------------------------------------------------


def test_call_blocked():
    """CALL statement is rejected by the SELECT/WITH whitelist."""
    is_valid, err = validate_sql("CALL some_proc()")
    assert not is_valid
    assert "Only SELECT" in (err or "")


def test_show_blocked():
    """SHOW statement is rejected by the SELECT/WITH whitelist."""
    is_valid, _ = validate_sql("SHOW TABLES")
    assert not is_valid


def test_cte_passes():
    """A WITH ... SELECT CTE is valid."""
    sql = "WITH ranked AS (SELECT id, name FROM teachers) SELECT * FROM ranked"
    is_valid, _ = validate_sql(sql)
    assert is_valid


# ---------------------------------------------------------------------------
# validate_sql — SELECT passes
# ---------------------------------------------------------------------------


def test_select_passes():
    """A plain SELECT statement is valid."""
    is_valid, err = validate_sql("SELECT * FROM teachers")
    assert is_valid
    assert err is None


def test_case_insensitive_select_passes():
    """validate_sql accepts SELECT in any case."""
    is_valid, _ = validate_sql("select name from teachers where id = 1")
    assert is_valid


def test_select_with_join_passes():
    """A multi-table SELECT with a JOIN is valid."""
    sql = "SELECT s.name FROM students s JOIN enrollments e ON e.student_id = s.id"
    is_valid, _ = validate_sql(sql)
    assert is_valid


# ---------------------------------------------------------------------------
# validate_sql — blocked DML / DDL keywords
# ---------------------------------------------------------------------------


def test_drop_blocked():
    """DROP TABLE is rejected."""
    is_valid, err = validate_sql("DROP TABLE teachers")
    assert not is_valid
    assert err is not None


def test_delete_blocked():
    """DELETE is rejected."""
    is_valid, _ = validate_sql("DELETE FROM students WHERE id = 1")
    assert not is_valid


def test_insert_blocked():
    """INSERT is rejected."""
    is_valid, _ = validate_sql("INSERT INTO teachers VALUES (1, 'Alice', 'a@uni.edu')")
    assert not is_valid


def test_update_blocked():
    """UPDATE is rejected."""
    is_valid, _ = validate_sql("UPDATE teachers SET name = 'Bob' WHERE id = 1")
    assert not is_valid


def test_alter_blocked():
    """ALTER TABLE is rejected."""
    is_valid, _ = validate_sql("ALTER TABLE teachers ADD COLUMN phone TEXT")
    assert not is_valid


# ---------------------------------------------------------------------------
# validate_sql — stacked statements
# ---------------------------------------------------------------------------


def test_stacked_statements_blocked():
    """A SELECT followed by DROP via semicolon is rejected."""
    is_valid, err = validate_sql("SELECT * FROM teachers; DROP TABLE teachers")
    assert not is_valid
    assert "Multiple statements" in (err or "")


def test_trailing_semicolon_passes():
    """A single trailing semicolon does not count as a stacked statement."""
    is_valid, _ = validate_sql("SELECT id FROM teachers;")
    assert is_valid


# ---------------------------------------------------------------------------
# validate_sql — blocked system schemas
# ---------------------------------------------------------------------------


def test_information_schema_blocked():
    """Queries against information_schema are rejected."""
    is_valid, err = validate_sql("SELECT * FROM information_schema.tables")
    assert not is_valid
    assert "information_schema" in (err or "")


def test_pg_catalog_blocked():
    """Queries against pg_catalog are rejected."""
    is_valid, _ = validate_sql("SELECT * FROM pg_catalog.pg_tables")
    assert not is_valid


# ---------------------------------------------------------------------------
# sql_validator node
# ---------------------------------------------------------------------------


def test_node_valid_sql_sets_executing(mock_tracer):
    """sql_validator node sets status to 'executing' when SQL is valid."""
    state = make_state(mock_tracer, sql="SELECT * FROM teachers")
    result = sql_validator(state)
    assert result["status"] == "executing"


def test_node_invalid_sql_sets_error(mock_tracer):
    """sql_validator node sets status to 'error' when SQL is unsafe."""
    state = make_state(mock_tracer, sql="DROP TABLE teachers")
    result = sql_validator(state)
    assert result["status"] == "error"
    assert "answer" in result


def test_node_logs_start_and_end(mock_tracer):
    """sql_validator node calls tracer.log for both START and END events."""
    state = make_state(mock_tracer, sql="SELECT 1")
    sql_validator(state)
    assert mock_tracer.log.call_count == 2
