"""Theme aggregation for a period.

Takes the free-text theme labels stored on issues and turns them into a ranked
list of ``{theme, count, examples}``:

1. **normalise** each label (lowercase, trim, collapse spaces),
2. **merge near-identical** labels (e.g. "photo upload crash" ≈ "photo-upload
   crashes") using string similarity,
3. **rank** the merged themes by how many issues mention them,
4. attach **representative example quotes** — the issues nearest the theme in
   pgvector embedding space (falls back to member quotes if embeddings/keys are
   unavailable).
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.issue import Issue
from app.models.ticket import Ticket
from app.schemas.summary import ThemeCount
from app.services.llm import LLMError
from app.services.vector_store import VectorStore

logger = get_logger(__name__)

# Two labels are "near-identical" at or above this similarity ratio.
_MERGE_THRESHOLD = 0.82
_EXAMPLES_PER_THEME = 3
_QUOTE_MAX = 200

# Fold common label variants to one canonical theme so semantically-identical
# themes aggregate even when the wording differs (string similarity alone can't
# tell that "login failure" == "account access"). Keyword -> canonical label.
_THEME_SYNONYMS: dict[str, str] = {
    "login": "account access",
    "log in": "account access",
    "sign in": "account access",
    "sign-in": "account access",
    "signin": "account access",
    "password": "account access",
    "locked out": "account access",
    "account access": "account access",
    "authentication": "account access",
    "credential": "account access",
    "duplicate charge": "duplicate charge",
    "double charge": "duplicate charge",
    "double charged": "duplicate charge",
    "charged twice": "duplicate charge",
    "duplicate subscription": "duplicate charge",
    "duplicate-subscription": "duplicate charge",
    "duplicate-charge": "duplicate charge",
    "refund": "refund request",
    "chargeback": "refund request",
    "money back": "refund request",
    "slow": "performance",
    "lag": "performance",
    "laggy": "performance",
    "freeze": "performance",
    "performance": "performance",
    "timeout": "performance",
    "times out": "performance",
    "crash": "app crash",
    "crashes": "app crash",
    "white screen": "app crash",
    "praise": "positive feedback",
    "compliment": "positive feedback",
    "positive feedback": "positive feedback",
    "thank": "positive feedback",
    "spam": "spam",
    "gibberish": "spam",
}


def _normalise_theme(label: str) -> str:
    """Lowercase, strip punctuation edges, collapse whitespace, canonicalise.

    A theme is folded to a canonical label when it contains a known synonym
    keyword (e.g. "login-page error" -> "account access"), so the same problem
    aggregates regardless of the exact phrasing the model chose.
    """
    cleaned = re.sub(r"\s+", " ", label.strip().lower()).strip(" .,-—:;")
    if not cleaned:
        return cleaned
    for keyword, canonical in _THEME_SYNONYMS.items():
        if keyword in cleaned:
            return canonical
    return cleaned


def issues_for_period(db: Session, user_id: UUID, week: str | None) -> list[Issue]:
    """Return this user's issues, optionally restricted to one ISO week."""
    stmt = (
        select(Issue).join(Ticket, Issue.ticket_id == Ticket.id).where(Ticket.owner_id == user_id)
    )
    if week is not None:
        stmt = stmt.where(Issue.week == week)
    return list(db.scalars(stmt))


def _example_quotes(
    db: Session,
    user_id: UUID,
    week: str | None,
    theme: str,
    fallback: list[str],
    vector_store: VectorStore | None,
) -> list[str]:
    """Pick example quotes nearest the theme via pgvector, else use fallbacks."""
    if vector_store is not None:
        try:
            query_vec = vector_store.embed_one(theme)
        except LLMError as exc:
            logger.warning("Theme embed failed; using fallback quotes: %s", exc)
            query_vec = None
        if query_vec is not None:
            stmt = (
                select(Issue.description)
                .join(Ticket, Issue.ticket_id == Ticket.id)
                .where(Ticket.owner_id == user_id)
                .where(Issue.embedding.is_not(None))
                .order_by(Issue.embedding.cosine_distance(query_vec))
                .limit(_EXAMPLES_PER_THEME)
            )
            if week is not None:
                stmt = stmt.where(Issue.week == week)
            quotes = [q for q in db.scalars(stmt) if q]
            if quotes:
                return [q[:_QUOTE_MAX] for q in quotes]
    return [q[:_QUOTE_MAX] for q in fallback[:_EXAMPLES_PER_THEME]]


def aggregate_themes(
    db: Session,
    user_id: UUID,
    *,
    week: str | None = None,
    limit: int = 10,
    vector_store: VectorStore | None = None,
    issues: list[Issue] | None = None,
) -> list[ThemeCount]:
    """Return the top ``limit`` merged themes for the period, ranked by count.

    Pass ``issues`` to reuse an already-loaded set; otherwise they are queried.
    """
    if issues is None:
        issues = issues_for_period(db, user_id, week)

    # Count normalised labels and remember an example quote for each.
    counts: dict[str, int] = {}
    examples: dict[str, list[str]] = {}
    for issue in issues:
        quote = issue.description or issue.title
        for raw_label in issue.themes:
            label = _normalise_theme(raw_label)
            if not label:
                continue
            counts[label] = counts.get(label, 0) + 1
            examples.setdefault(label, [])
            if quote and quote not in examples[label]:
                examples[label].append(quote)

    # Merge near-identical labels; the highest-count label becomes canonical.
    canon: list[str] = []
    members: dict[str, list[str]] = {}
    for label in sorted(counts, key=lambda lbl: (-counts[lbl], lbl)):
        match = next(
            (c for c in canon if SequenceMatcher(None, label, c).ratio() >= _MERGE_THRESHOLD),
            None,
        )
        if match is not None:
            members[match].append(label)
        else:
            canon.append(label)
            members[label] = [label]

    merged = [(c, sum(counts[m] for m in members[c])) for c in canon]
    merged.sort(key=lambda t: (-t[1], t[0]))

    result: list[ThemeCount] = []
    for theme, count in merged[:limit]:
        fallback = [q for m in members[theme] for q in examples.get(m, [])]
        quotes = _example_quotes(db, user_id, week, theme, fallback, vector_store)
        result.append(ThemeCount(theme=theme, count=count, examples=quotes))
    return result
