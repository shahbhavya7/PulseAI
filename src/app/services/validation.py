"""Validation: file-level checks and per-item content-quality checks.

Runs entirely *before* any AI. Groups four concerns that all answer "is this
input usable, and how?":

* **Errors** — typed, client-fixable failures that abort a whole upload.
* **Decoding** — bytes → text with encoding auto-repair (:func:`decode_bytes`).
* **File-level** — CSV text-column discovery and blank detection.
* **Per-item** — empty / one-word / junk classification (:func:`classify_content`).

PII redaction, boilerplate stripping, and hashing live in
:mod:`app.services.cleaning`; parsing and orchestration in
:mod:`app.services.ingestion`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from app.models.enums import IssueFlag

# ---------------------------------------------------------------------------
# Typed ingestion errors (file-level; mapped to 4xx by the route)
# ---------------------------------------------------------------------------


class IngestionError(Exception):
    """Base class for file-level ingestion failures (client-fixable)."""

    code: str = "ingestion_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFileTypeError(IngestionError):
    """The uploaded file's type has no registered parser."""

    code = "unsupported_file_type"


class UndecodableFileError(IngestionError):
    """The bytes could not be decoded to plausible text. Remedy: re-save as UTF-8."""

    code = "undecodable_file"


class MissingTextColumnError(IngestionError):
    """A CSV upload lacks any recognizable text column."""

    code = "missing_text_column"


class EmptyFileError(IngestionError):
    """The uploaded file contains no usable content at all."""

    code = "empty_file"


# ---------------------------------------------------------------------------
# Decoding with encoding auto-repair
# ---------------------------------------------------------------------------

_FALLBACK_ENCODINGS: tuple[str, ...] = ("cp1252", "latin-1")  # latin-1 = universal
_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")
_ASK_FOR_UTF8 = "Could not decode the file. Please re-save it as UTF-8 and try again."


@dataclass(frozen=True)
class DecodedText:
    """The decoded text plus how it was obtained."""

    text: str
    encoding: str
    recovered: bool  # True when a non-UTF-8 fallback was needed


def _reject_if_binary(text: str) -> None:
    """Raise if ``text`` contains NUL — a reliable signal of binary/mojibake."""
    if "\x00" in text:
        raise UndecodableFileError(_ASK_FOR_UTF8)


def decode_bytes(data: bytes) -> DecodedText:
    """Decode ``data`` to text, repairing common non-UTF-8 encodings.

    Order: strict UTF-8 → BOM (utf-8-sig / utf-16) → cp1252 → latin-1. A decoded
    result containing NUL is treated as binary and rejected.

    Raises:
        UndecodableFileError: If the bytes cannot be decoded to plausible text.
    """
    if not data:
        return DecodedText(text="", encoding="utf-8", recovered=False)

    try:
        return DecodedText(text=data.decode("utf-8"), encoding="utf-8", recovered=False)
    except UnicodeDecodeError:
        pass

    if data.startswith(_UTF8_BOM):
        return DecodedText(data.decode("utf-8-sig"), "utf-8-sig", recovered=True)
    if data.startswith(_UTF16_BOMS):
        text = data.decode("utf-16")
        _reject_if_binary(text)
        return DecodedText(text, "utf-16", recovered=True)

    for encoding in _FALLBACK_ENCODINGS:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            continue
        _reject_if_binary(text)
        return DecodedText(text, encoding, recovered=True)

    raise UndecodableFileError(_ASK_FOR_UTF8)


# ---------------------------------------------------------------------------
# CSV file-level validation
# ---------------------------------------------------------------------------

# Column names accepted as "the text column", in priority order (case-insensitive).
TEXT_COLUMN_CANDIDATES: tuple[str, ...] = (
    "text",
    "body",
    "message",
    "description",
    "content",
    "comment",
    "comments",
    "ticket",
    "issue",
    "feedback",
    "review",
)


def find_text_column(columns: Sequence[str]) -> str:
    """Return the name of the text column for a CSV, or raise.

    A single-column CSV uses that column implicitly. Otherwise a column whose
    name matches :data:`TEXT_COLUMN_CANDIDATES` is required.

    Raises:
        MissingTextColumnError: With a clear, named message when none is found.
    """
    cleaned = [c for c in columns if c and c.strip()]
    if not cleaned:
        raise MissingTextColumnError("The CSV has no readable header row.")
    if len(cleaned) == 1:
        return columns[0]

    lookup = {c.strip().lower(): c for c in cleaned}
    for candidate in TEXT_COLUMN_CANDIDATES:
        if candidate in lookup:
            return lookup[candidate]

    raise MissingTextColumnError(
        "Could not find a text column. Expected one of "
        f"{', '.join(TEXT_COLUMN_CANDIDATES)}; got: {', '.join(cleaned)}. "
        "Rename your text column to 'text' and re-upload."
    )


def is_blank(value: object) -> bool:
    """Return True for None, NaN-like, or whitespace-only values."""
    if value is None:
        return True
    text = str(value).strip()
    return text == "" or text.lower() == "nan"


# ---------------------------------------------------------------------------
# Per-item content-quality classification (empty / one-word / junk)
# ---------------------------------------------------------------------------

# A token with at least one letter (tells words from punctuation/numbers).
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass
class ContentClass:
    """Verdict on whether an item is substantive enough to be a real issue."""

    is_junk: bool
    confidence: float  # confidence that this IS a valid issue, in [0, 1]
    flags: list[str] = field(default_factory=list)


def classify_content(text: str) -> ContentClass:
    """Classify cleaned text as empty / one-word / junk / valid, with confidence.

    ``confidence`` expresses how likely the item is a genuine issue: high for
    normal prose, low for one-word or junk (letter-poor) content, zero for empty.
    """
    stripped = text.strip()
    if not stripped:
        return ContentClass(is_junk=True, confidence=0.0, flags=[IssueFlag.JUNK.value])

    words = _WORD_RE.findall(stripped)
    tokens = stripped.split()

    if len(words) == 0:  # digits / punctuation only — no actual words
        return ContentClass(is_junk=True, confidence=0.1, flags=[IssueFlag.JUNK.value])

    if len(tokens) == 1:
        return ContentClass(
            is_junk=True,
            confidence=0.3,
            flags=[IssueFlag.ONE_WORD.value, IssueFlag.JUNK.value],
        )

    # Ratio of "wordy" characters to non-space characters. Low = gibberish → junk.
    letters = sum(len(w) for w in words)
    non_space = len(re.sub(r"\s", "", stripped))
    letter_ratio = letters / non_space if non_space else 0.0
    if letter_ratio < 0.5:
        return ContentClass(is_junk=True, confidence=0.2, flags=[IssueFlag.JUNK.value])

    confidence = min(0.95, 0.6 + 0.05 * len(tokens))
    return ContentClass(is_junk=False, confidence=round(confidence, 2), flags=[])
