"""
Top-level fixtures shared across all test modules.

Provides:
    sqlite_connector  -- a fresh in-memory SQLiteConnector for each test
    seeded_connector  -- sqlite_connector with full university schema + seed data
    mock_tracer       -- a MagicMock(spec=Tracer) whose log() is a no-op
"""

from unittest.mock import MagicMock

import pytest

from agent.tracing import Tracer
from db.sqlite import SQLiteConnector

_DDL = """
CREATE TABLE teachers (
    id    INTEGER PRIMARY KEY,
    name  TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL
);

CREATE TABLE students (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL,
    enrollment_year INTEGER NOT NULL
);

CREATE TABLE courses (
    id      INTEGER PRIMARY KEY,
    name    TEXT NOT NULL,
    credits INTEGER NOT NULL
);

CREATE TABLE semesters (
    id     INTEGER PRIMARY KEY,
    name   TEXT NOT NULL,
    year   INTEGER NOT NULL,
    season TEXT NOT NULL CHECK (season IN ('spring', 'summer', 'fall'))
);

CREATE TABLE course_offerings (
    id           INTEGER PRIMARY KEY,
    course_id    INTEGER NOT NULL,
    teacher_id   INTEGER NOT NULL,
    semester_id  INTEGER NOT NULL,
    syllabus_url TEXT,
    room         TEXT,
    max_capacity INTEGER,
    FOREIGN KEY (course_id)   REFERENCES courses(id),
    FOREIGN KEY (teacher_id)  REFERENCES teachers(id),
    FOREIGN KEY (semester_id) REFERENCES semesters(id)
);

CREATE TABLE enrollments (
    id          INTEGER PRIMARY KEY,
    student_id  INTEGER NOT NULL,
    offering_id INTEGER NOT NULL,
    grade       REAL,
    enrolled_at TEXT NOT NULL,
    FOREIGN KEY (student_id)  REFERENCES students(id),
    FOREIGN KEY (offering_id) REFERENCES course_offerings(id)
);
"""

_SEED = """
INSERT INTO teachers VALUES (1, 'Alice Smith', 'alice@university.edu');
INSERT INTO teachers VALUES (2, 'Bob Jones',   'bob@university.edu');

INSERT INTO students VALUES (1, 'Charlie Brown', 'charlie@student.edu', 2022);
INSERT INTO students VALUES (2, 'Diana Prince',  'diana@student.edu',   2023);
INSERT INTO students VALUES (3, 'Eve Adams',     'eve@student.edu',     2022);

INSERT INTO courses VALUES (1, 'Algorithms', 3);
INSERT INTO courses VALUES (2, 'Databases',  4);

INSERT INTO semesters VALUES (1, 'Fall 2024',   2024, 'fall');
INSERT INTO semesters VALUES (2, 'Spring 2025', 2025, 'spring');

INSERT INTO course_offerings VALUES (1, 1, 1, 1, NULL, 'Room 101', 30);
INSERT INTO course_offerings VALUES (2, 2, 2, 1, NULL, 'Room 202', 25);
INSERT INTO course_offerings VALUES (3, 1, 1, 2, NULL, 'Room 101', 30);

INSERT INTO enrollments VALUES (1, 1, 1, 95.5, '2024-09-01T10:00:00');
INSERT INTO enrollments VALUES (2, 2, 1, 88.0, '2024-09-01T10:00:00');
INSERT INTO enrollments VALUES (3, 3, 1, 72.5, '2024-09-01T10:00:00');
INSERT INTO enrollments VALUES (4, 1, 2, 91.0, '2024-09-01T10:00:00');
INSERT INTO enrollments VALUES (5, 2, 3, NULL, '2025-01-15T10:00:00');
"""


@pytest.fixture
async def sqlite_connector():
    """
    Yield a fresh SQLiteConnector backed by an in-memory database.

    The connection is closed after each test, ensuring full isolation.
    """
    conn = SQLiteConnector(":memory:")
    yield conn
    await conn.close()


@pytest.fixture
async def seeded_connector(sqlite_connector):
    """
    Yield a SQLiteConnector with the full university schema and seed data applied.

    Suitable for any test that needs to run real SQL against the university tables.
    """
    conn = await sqlite_connector._get_conn()
    await conn.executescript(_DDL + _SEED)
    yield sqlite_connector


@pytest.fixture
def mock_tracer() -> MagicMock:
    """
    Return a MagicMock with the Tracer interface whose log() is a no-op.

    Use this in agent node tests to satisfy the AgentState tracer field
    without producing any log output.
    """
    return MagicMock(spec=Tracer)
