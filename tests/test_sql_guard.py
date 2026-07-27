"""Guardrail tests for LLM-generated SQL.

These are security tests: each one asserts that a specific attack or mistake is
rejected BEFORE any database work happens. If one of these ever fails, chat can
write to (or read outside of) the user's own data.
"""

from __future__ import annotations

import pytest

from app.services.sql_guard import SQLGuardError, validate_sql

# A minimal query that satisfies every rule; the attack cases mutate this shape.
GOOD = (
    "SELECT count(*) AS n FROM issues "
    "JOIN tickets ON issues.ticket_id = tickets.id "
    "WHERE tickets.owner_id = :user_id"
)


def test_accepts_a_valid_scoped_select() -> None:
    assert validate_sql(GOOD).startswith("SELECT")


def test_accepts_cte_and_strips_trailing_semicolon() -> None:
    sql = (
        "WITH weekly AS ("
        "  SELECT issues.week AS w, count(*) AS n FROM issues"
        "  JOIN tickets ON issues.ticket_id = tickets.id"
        "  WHERE tickets.owner_id = :user_id GROUP BY issues.week"
        ") SELECT * FROM weekly LIMIT 10;"
    )
    out = validate_sql(sql)
    assert not out.endswith(";")
    assert out.lower().startswith("with")


def test_strips_markdown_fences() -> None:
    assert validate_sql(f"```sql\n{GOOD}\n```").startswith("SELECT")


# ---------------------------------------------------------------------------
# Write attempts — every one of these must be refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM issues WHERE tickets.owner_id = :user_id",
        "INSERT INTO issues (title) VALUES ('x')",
        "UPDATE issues SET title = 'x' WHERE tickets.owner_id = :user_id",
        "DROP TABLE issues",
        "TRUNCATE issues",
        "ALTER TABLE issues ADD COLUMN x int",
        "GRANT ALL ON issues TO public",
    ],
)
def test_rejects_write_statements(sql: str) -> None:
    with pytest.raises(SQLGuardError):
        validate_sql(sql)


def test_rejects_stacked_statement_after_select() -> None:
    """The classic injection: a harmless SELECT followed by a destructive one."""
    with pytest.raises(SQLGuardError, match="Multiple statements"):
        validate_sql(f"{GOOD}; DROP TABLE issues")


def test_rejects_write_hidden_behind_a_comment() -> None:
    """Comments are stripped before checking, so this cannot smuggle a verb."""
    with pytest.raises(SQLGuardError):
        validate_sql(f"{GOOD} /* */ ; DELETE FROM issues")


def test_rejects_cte_that_writes() -> None:
    sql = (
        "WITH gone AS (DELETE FROM issues RETURNING id) "
        "SELECT count(*) FROM issues JOIN tickets ON issues.ticket_id = tickets.id "
        "WHERE tickets.owner_id = :user_id"
    )
    with pytest.raises(SQLGuardError):
        validate_sql(sql)


# ---------------------------------------------------------------------------
# Scoping and table access
# ---------------------------------------------------------------------------


def test_rejects_query_without_user_scoping() -> None:
    """No :user_id bind means it could read every user's rows."""
    with pytest.raises(SQLGuardError, match="user_id"):
        validate_sql("SELECT count(*) AS n FROM issues")


def test_rejects_reading_the_users_table() -> None:
    """Credentials must be unreachable even in a pure SELECT."""
    with pytest.raises(SQLGuardError, match="not allowed"):
        validate_sql("SELECT email, password_hash FROM users WHERE id = :user_id")


def test_rejects_reading_chat_transcripts() -> None:
    with pytest.raises(SQLGuardError, match="not allowed"):
        validate_sql("SELECT content FROM chat_messages WHERE id = :user_id")


def test_rejects_catalog_introspection() -> None:
    with pytest.raises(SQLGuardError):
        validate_sql("SELECT tablename FROM pg_catalog.pg_tables WHERE x = :user_id")


def test_rejects_file_read_function() -> None:
    with pytest.raises(SQLGuardError):
        validate_sql("SELECT pg_read_file('/etc/passwd') FROM issues WHERE x = :user_id")


def test_rejects_sleep_dos() -> None:
    with pytest.raises(SQLGuardError):
        validate_sql("SELECT pg_sleep(60) FROM issues WHERE x = :user_id")


def test_rejects_empty_input() -> None:
    with pytest.raises(SQLGuardError):
        validate_sql("   ")


def test_allows_lateral_jsonb_expansion() -> None:
    """Counting themes needs CROSS JOIN LATERAL; it must not read as a table."""
    sql = (
        "SELECT theme, count(*) AS n FROM issues i "
        "JOIN tickets t ON t.id = i.ticket_id "
        "CROSS JOIN LATERAL jsonb_array_elements_text(i.themes) AS theme "
        "WHERE t.owner_id = :user_id GROUP BY theme LIMIT 5"
    )
    assert validate_sql(sql)


def test_lateral_does_not_smuggle_a_forbidden_table() -> None:
    """Skipping the LATERAL keyword must not skip the allowlist check itself."""
    sql = (
        "SELECT * FROM issues i JOIN tickets t ON t.id = i.ticket_id "
        "CROSS JOIN LATERAL users u WHERE t.owner_id = :user_id"
    )
    with pytest.raises(SQLGuardError, match="not allowed"):
        validate_sql(sql)


def test_subquery_in_from_is_not_read_as_a_table() -> None:
    sql = (
        "SELECT x.category, count(*) AS n FROM ("
        "  SELECT i.category FROM issues i JOIN tickets t ON t.id = i.ticket_id"
        "  WHERE t.owner_id = :user_id"
        ") x GROUP BY x.category"
    )
    assert validate_sql(sql)


def test_updated_at_column_is_not_mistaken_for_update() -> None:
    """Word-boundary matching: a legitimate column must not trip the denylist."""
    sql = (
        "SELECT max(issues.created_at) AS latest FROM issues "
        "JOIN tickets ON issues.ticket_id = tickets.id "
        "WHERE tickets.owner_id = :user_id"
    )
    assert validate_sql(sql)
