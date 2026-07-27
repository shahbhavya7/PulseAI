"""Guardrails for LLM-generated SQL — the security boundary for chat analytics.

The model writes SQL to answer comparison questions ("critical issues this week
vs last"). That SQL is UNTRUSTED. This module is the gate it must pass before
touching the database, and it is deliberately paranoid: everything is denied
unless explicitly allowed.

Four independent layers, each of which alone would stop a write:

1. **Statement shape** — exactly one statement, and it must start with SELECT or
   WITH. No semicolon-chained second statement, no multi-statement payloads.
2. **Keyword denylist** — any DML/DDL/permission verb (INSERT, UPDATE, DELETE,
   DROP, ALTER, GRANT, COPY, pg_sleep, …) anywhere in the statement is rejected,
   matched on word boundaries so a column named ``updated_at`` is still fine.
3. **Table allowlist** — only the analytics tables may be referenced. Auth and
   transcript tables (``users``, ``chat_messages``, …) are not reachable at all,
   so a leaked prompt cannot exfiltrate password hashes.
4. **Mandatory user scoping** — the statement must filter by the acting user's
   id via the ``:user_id`` bind parameter. Combined with (3) this means a query
   can only ever see rows the caller already owns.

Execution adds two more runtime protections that do not depend on the text
check: a READ ONLY transaction (Postgres itself rejects any write, even one
that somehow slipped past the parser) and a statement timeout.

Nothing here trusts the model. If any layer is unsure, it rejects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.logging import get_logger

logger = get_logger(__name__)


class SQLGuardError(Exception):
    """Generated SQL failed a safety check and was not executed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# Tables the analytics query may read. Deliberately excludes users,
# chat_sessions, chat_messages, session_summaries and alembic_version: chat has
# no business reading credentials or transcripts, so they are simply unreachable.
ALLOWED_TABLES: frozenset[str] = frozenset({"issues", "tickets"})

# Verbs that must never appear. Word-boundary matched, so `updated_at` (a column)
# does not trip the `update` rule.
_FORBIDDEN_KEYWORDS: tuple[str, ...] = (
    "insert",
    "update",
    "delete",
    "drop",
    "truncate",
    "alter",
    "create",
    "grant",
    "revoke",
    "commit",
    "rollback",
    "savepoint",
    "vacuum",
    "analyze",
    "reindex",
    "cluster",
    "copy",
    "call",
    "do",
    "execute",
    "prepare",
    "listen",
    "notify",
    "lock",
    "set",
    "reset",
    "refresh",
    "import",
    "merge",
    "upsert",
    "returning",
    "into",
)

# Functions/constructs that read the filesystem, sleep, or reach outside the
# query. pg_read_file and friends are how a read-only query still becomes a leak.
_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "lo_import",
    "lo_export",
    "dblink",
    "pg_stat_file",
    "current_setting",
    "set_config",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_authid",
    "pg_shadow",
    "pg_user",
    "information_schema",
    "pg_catalog",
)

# The bind parameter the query must scope on. Passing the id as a bind (never
# string-interpolated) also removes any chance of quoting/injection on our side.
_USER_BIND = "user_id"

_COMMENT_BLOCK = re.compile(r"/\*.*?\*/", re.DOTALL)
_COMMENT_LINE = re.compile(r"--[^\n]*")
_FENCE = re.compile(r"^```(?:sql)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)
# Matches the identifier after FROM / JOIN, optionally preceded by LATERAL and
# optionally schema-qualified. The trailing group captures whether a "(" follows:
# if it does, this is a set-returning function call (e.g.
# `CROSS JOIN LATERAL jsonb_array_elements_text(...)`), not a table, and the
# allowlist check skips it. Callers must test group(2) before trusting group(1).
_TABLE_REF = re.compile(
    r"\b(?:from|join)\s+(?:lateral\s+)?([a-zA-Z_][\w.]*)(\s*\()?",
    re.IGNORECASE,
)


@dataclass
class QueryResult:
    """Rows returned by a validated analytics query."""

    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.rows


def _strip_noise(sql: str) -> str:
    """Remove markdown fences and SQL comments.

    Comments are stripped before validation so a payload cannot hide a forbidden
    keyword behind ``--`` or ``/* */`` and have it execute anyway.
    """
    cleaned = _FENCE.sub("", sql.strip())
    cleaned = _COMMENT_BLOCK.sub(" ", cleaned)
    cleaned = _COMMENT_LINE.sub(" ", cleaned)
    return cleaned.strip()


def validate_sql(sql: str) -> str:
    """Return the normalised SQL, or raise :class:`SQLGuardError`.

    Applies every layer described in the module docstring. The returned string
    is what should be executed; callers must not re-edit it afterwards.
    """
    if not sql or not sql.strip():
        raise SQLGuardError("Empty SQL.")

    cleaned = _strip_noise(sql)
    if not cleaned:
        raise SQLGuardError("SQL was only comments.")

    # Layer 1a: exactly one statement. A trailing semicolon is fine; anything
    # after it is not, which kills "SELECT 1; DROP TABLE issues".
    body = cleaned.rstrip(";").strip()
    if ";" in body:
        raise SQLGuardError("Multiple statements are not allowed.")

    lowered = body.lower()

    # Layer 1b: must be a read. WITH is allowed so CTEs work, but a data-writing
    # CTE would still be caught by the keyword layer below.
    if not (lowered.startswith("select") or lowered.startswith("with")):
        raise SQLGuardError("Only SELECT statements are allowed.")

    # Layer 2: forbidden verbs, on word boundaries.
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise SQLGuardError(f"Forbidden keyword in query: {keyword}.")
    for pattern in _FORBIDDEN_PATTERNS:
        if pattern in lowered:
            raise SQLGuardError(f"Forbidden construct in query: {pattern}.")

    # Layer 3: every referenced table must be on the allowlist. A name followed
    # by "(" is a function call (jsonb_array_elements_text, unnest, …), not a
    # table, so it is not subject to the table allowlist; the forbidden-pattern
    # layer above is what keeps dangerous functions out.
    referenced = {
        m.group(1).lower().split(".")[-1] for m in _TABLE_REF.finditer(body) if not m.group(2)
    }
    # CTE names are self-references, not real tables; allow them.
    cte_names = {
        m.group(1).lower() for m in re.finditer(r"\b([a-zA-Z_]\w*)\s+as\s*\(", body, re.IGNORECASE)
    }
    unknown = referenced - ALLOWED_TABLES - cte_names
    if unknown:
        raise SQLGuardError(f"Query references tables that are not allowed: {sorted(unknown)}.")
    if not referenced & ALLOWED_TABLES:
        raise SQLGuardError("Query must read from the analytics tables.")

    # Layer 4: mandatory user scoping via the bind parameter.
    if f":{_USER_BIND}" not in body:
        raise SQLGuardError("Query must filter by :user_id.")

    return body


def run_readonly_query(
    db: Session,
    sql: str,
    user_id: UUID,
    *,
    max_rows: int = 50,
    timeout_ms: int = 5000,
) -> QueryResult:
    """Validate then execute ``sql`` in a READ ONLY transaction.

    Args:
        db: Session to borrow a connection from.
        sql: Untrusted, model-generated SQL.
        user_id: Bound to ``:user_id``; the query is required to filter on it.
        max_rows: Hard cap on returned rows, so a runaway query cannot flood the
            prompt or the response.
        timeout_ms: Postgres-side statement timeout.

    Raises:
        SQLGuardError: If validation fails or execution errors.
    """
    validated = validate_sql(sql)

    # A nested transaction we always roll back. `SET TRANSACTION READ ONLY` makes
    # Postgres itself refuse writes, so this holds even if the text checks above
    # were somehow bypassed. Defense in depth: the parser is not the only guard.
    savepoint = db.begin_nested()
    try:
        db.execute(text(f"SET LOCAL statement_timeout = {int(timeout_ms)}"))
        db.execute(text("SET TRANSACTION READ ONLY"))
        result = db.execute(text(validated), {_USER_BIND: str(user_id)})
        columns = list(result.keys())
        fetched = result.fetchmany(max_rows + 1)
    except SQLGuardError:
        raise
    except Exception as exc:  # noqa: BLE001 — a bad generated query must not 500
        logger.info("Generated SQL failed to execute: %s", exc)
        raise SQLGuardError(f"Query could not be executed: {exc}") from exc
    finally:
        # Always discard: nothing this query did may ever persist.
        savepoint.rollback()

    truncated = len(fetched) > max_rows
    rows = [list(r) for r in fetched[:max_rows]]
    return QueryResult(columns=columns, rows=rows, truncated=truncated)
