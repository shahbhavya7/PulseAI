"""The no-em-dash rule for AI output is enforced at the boundary, not just the
prompt. These are pure-function tests (no model call)."""

from __future__ import annotations

from app.services.llm import strip_em_dashes


def test_spaced_em_dash_becomes_comma() -> None:
    assert strip_em_dashes("You have 1 issue — it is critical.") == (
        "You have 1 issue, it is critical."
    )


def test_tight_em_dash_becomes_comma() -> None:
    assert strip_em_dashes("A—B—C") == "A, B, C"


def test_en_dash_is_also_removed() -> None:
    assert strip_em_dashes("range 0 – 1") == "range 0, 1"


def test_no_dash_is_unchanged() -> None:
    text = "Categories: other 6, bug 3, incident 2."
    assert strip_em_dashes(text) == text


def test_hyphenated_theme_labels_are_preserved() -> None:
    # Real theme labels use hyphens, not em/en dashes, so they must survive.
    assert strip_em_dashes("photo-upload crash") == "photo-upload crash"


def test_no_double_comma_left_behind() -> None:
    assert "  " not in strip_em_dashes("first, — second")
    assert ",," not in strip_em_dashes("first, — second")
