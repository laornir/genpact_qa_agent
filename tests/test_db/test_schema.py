from db.schema_loader import load_schema_context

EXPECTED_TABLES = {
    "teachers",
    "students",
    "courses",
    "semesters",
    "course_offerings",
    "enrollments",
}

EXPECTED_FKS = {
    ("course_offerings", "course_id"): "courses.id",
    ("course_offerings", "teacher_id"): "teachers.id",
    ("course_offerings", "semester_id"): "semesters.id",
    ("enrollments", "student_id"): "students.id",
    ("enrollments", "offering_id"): "course_offerings.id",
}


async def test_fetch_schema_returns_all_tables(seeded_connector):
    """fetch_schema includes a row for every expected table."""
    rows = await seeded_connector.fetch_schema()
    assert {r["table"] for r in rows} == EXPECTED_TABLES


async def test_fetch_schema_row_shape(seeded_connector):
    """Every row returned by fetch_schema has exactly the five expected keys."""
    rows = await seeded_connector.fetch_schema()
    for row in rows:
        assert set(row.keys()) == {"table", "column", "type", "is_fk", "references"}


async def test_fetch_schema_fk_columns(seeded_connector):
    """FK columns are marked is_fk=True with the correct 'table.column' reference."""
    rows = await seeded_connector.fetch_schema()
    fk_index = {(r["table"], r["column"]): r["references"] for r in rows if r["is_fk"]}
    for (table, col), expected_ref in EXPECTED_FKS.items():
        assert (table, col) in fk_index, f"Expected FK on {table}.{col}"
        assert fk_index[(table, col)] == expected_ref


async def test_fetch_schema_non_fk_columns_have_no_references(seeded_connector):
    """Non-FK columns always have references=None."""
    rows = await seeded_connector.fetch_schema()
    for row in rows:
        if not row["is_fk"]:
            assert row["references"] is None


async def test_fetch_schema_no_spurious_fks(seeded_connector):
    """No column is incorrectly flagged as a FK beyond the five expected ones."""
    rows = await seeded_connector.fetch_schema()
    fk_cols = {(r["table"], r["column"]) for r in rows if r["is_fk"]}
    assert fk_cols == set(EXPECTED_FKS.keys())


async def test_schema_context_arrow_notation(seeded_connector):
    """FK columns appear in the context string with arrow notation (col→table.id)."""
    ctx = await load_schema_context(seeded_connector)
    assert "course_id→courses.id" in ctx
    assert "teacher_id→teachers.id" in ctx
    assert "student_id→students.id" in ctx
    assert "offering_id→course_offerings.id" in ctx


async def test_schema_context_plain_columns(seeded_connector):
    """Non-FK tables render as 'table: col1, col2, ...' with no arrow notation."""
    ctx = await load_schema_context(seeded_connector)
    assert "teachers: id, name, email" in ctx
    assert "students: id, name, email, enrollment_year" in ctx
    assert "courses: id, name, credits" in ctx


async def test_schema_context_contains_all_tables(seeded_connector):
    """Every table in the schema appears at least once in the context string."""
    ctx = await load_schema_context(seeded_connector)
    for table in EXPECTED_TABLES:
        assert table in ctx
