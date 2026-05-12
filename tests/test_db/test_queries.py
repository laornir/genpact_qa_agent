import sqlite3

import pytest


async def test_healthcheck(seeded_connector):
    """healthcheck returns True when the database is reachable."""
    assert await seeded_connector.healthcheck() is True


async def test_select_all_rows(seeded_connector):
    """execute_query returns one dict per row for a full-table SELECT."""
    rows = await seeded_connector.execute_query("SELECT * FROM teachers")
    assert len(rows) == 2


async def test_select_returns_dicts(seeded_connector):
    """Each row is a dict keyed by column name with correct values."""
    rows = await seeded_connector.execute_query("SELECT id, name FROM teachers ORDER BY id")
    assert rows[0] == {"id": 1, "name": "Alice Smith"}
    assert rows[1] == {"id": 2, "name": "Bob Jones"}


async def test_where_filter(seeded_connector):
    """WHERE clause correctly filters rows by a scalar column value."""
    rows = await seeded_connector.execute_query(
        "SELECT * FROM students WHERE enrollment_year = 2022"
    )
    assert len(rows) == 2
    assert all(r["enrollment_year"] == 2022 for r in rows)


async def test_empty_result(seeded_connector):
    """A SELECT that matches no rows returns an empty list, not an error."""
    rows = await seeded_connector.execute_query("SELECT * FROM teachers WHERE id = 9999")
    assert rows == []


async def test_join_students_to_courses(seeded_connector):
    """A four-table JOIN resolves enrollments to student and course names correctly."""
    sql = """
        SELECT s.name AS student, c.name AS course
        FROM enrollments e
        JOIN students s         ON s.id  = e.student_id
        JOIN course_offerings o ON o.id  = e.offering_id
        JOIN courses c          ON c.id  = o.course_id
        ORDER BY s.name, c.name
    """
    rows = await seeded_connector.execute_query(sql)
    assert len(rows) == 5
    assert {"student": "Charlie Brown", "course": "Algorithms"} in rows
    assert {"student": "Charlie Brown", "course": "Databases"} in rows


async def test_count_aggregate(seeded_connector):
    """COUNT(*) returns the total number of enrollment rows in the seed data."""
    rows = await seeded_connector.execute_query("SELECT COUNT(*) AS cnt FROM enrollments")
    assert rows[0]["cnt"] == 5


async def test_avg_grade_per_course(seeded_connector):
    """AVG(grade) grouped by course ignores NULL grades and computes correctly."""
    sql = """
        SELECT c.name, AVG(e.grade) AS avg_grade
        FROM enrollments e
        JOIN course_offerings o ON o.id = e.offering_id
        JOIN courses c          ON c.id = o.course_id
        WHERE e.grade IS NOT NULL
        GROUP BY c.name
        ORDER BY c.name
    """
    rows = await seeded_connector.execute_query(sql)
    algo = next(r for r in rows if r["name"] == "Algorithms")
    assert round(algo["avg_grade"], 2) == round((95.5 + 88.0 + 72.5) / 3, 2)


async def test_null_grade_filter(seeded_connector):
    """WHERE grade IS NULL returns only the one ungraded enrollment in the seed data."""
    rows = await seeded_connector.execute_query("SELECT * FROM enrollments WHERE grade IS NULL")
    assert len(rows) == 1
    assert rows[0]["student_id"] == 2


async def test_fk_violation_raises(seeded_connector):
    """Inserting an enrollment with a non-existent student_id raises IntegrityError."""
    conn = await seeded_connector._get_conn()
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO enrollments (student_id, offering_id, enrolled_at)"
            " VALUES (9999, 1, '2024-01-01')"
        )
        await conn.commit()


async def test_unique_constraint_raises(seeded_connector):
    """Inserting a teacher with a duplicate email raises IntegrityError."""
    conn = await seeded_connector._get_conn()
    with pytest.raises(sqlite3.IntegrityError):
        await conn.execute(
            "INSERT INTO teachers (name, email) VALUES ('Dup', 'alice@university.edu')"
        )
        await conn.commit()
