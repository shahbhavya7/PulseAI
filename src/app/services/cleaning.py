"""Per-item text cleaning: boilerplate stripping, PII redaction, language, hashing.

Every function here is pure and deterministic (``langdetect`` is seeded), so each
edge case is unit-testable directly. The ingestion pipeline
(:mod:`app.services.ingestion`) applies them in this order::

    strip_boilerplate → redact_pii → detect_language → normalise_text → content_hash

The **redacted** text is what gets stored; the **normalised** text is what gets
hashed for dedup. Content-quality (empty/one-word/junk) checks live in
:mod:`app.services.validation`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from uuid import UUID

from langdetect import DetectorFactory, LangDetectException, detect

# Make langdetect deterministic (it is randomized by default).
DetectorFactory.seed = 0

# ---------------------------------------------------------------------------
# Boilerplate / signature / quoted-reply stripping
# ---------------------------------------------------------------------------

_ON_WROTE_RE = re.compile(r"^\s*On .+ wrote:\s*$", re.IGNORECASE)
_ORIGINAL_MSG_RE = re.compile(r"^\s*-{2,}\s*Original Message\s*-{2,}\s*$", re.IGNORECASE)
_SIG_DELIM_RE = re.compile(r"^--\s*$")  # RFC 3676 signature delimiter
_SIG_OPENER_RE = re.compile(
    r"^\s*(best regards|kind regards|regards|thanks|thank you|cheers|sincerely|"
    r"sent from my \w+)\b.*$",
    re.IGNORECASE,
)
_QUOTE_LINE_RE = re.compile(r"^\s*>")


@dataclass
class CleanResult:
    """Output of :func:`strip_boilerplate`."""

    text: str
    boilerplate_stripped: bool


def strip_boilerplate(text: str) -> CleanResult:
    """Remove signatures, quoted replies, and original-message trailers.

    Everything from the first quoted-reply / original-message / signature marker
    onward is dropped, as are individual ``>`` quote lines above it.
    """
    kept: list[str] = []
    stripped = False
    for line in text.splitlines():
        if _ON_WROTE_RE.match(line) or _ORIGINAL_MSG_RE.match(line):
            stripped = True
            break  # quoted original follows — drop the rest
        if _SIG_DELIM_RE.match(line) or _SIG_OPENER_RE.match(line):
            stripped = True
            break  # signature block follows — drop the rest
        if _QUOTE_LINE_RE.match(line):
            stripped = True
            continue  # drop quoted lines but keep scanning
        kept.append(line)
    return CleanResult(text="\n".join(kept).strip(), boilerplate_stripped=stripped)


# ---------------------------------------------------------------------------
# PII redaction
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,16}\b")  # 13–16 digits, grouped
_PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}(?!\w)")

EMAIL_TOKEN = "[REDACTED_EMAIL]"
CARD_TOKEN = "[REDACTED_CARD]"
PHONE_TOKEN = "[REDACTED_PHONE]"


def _luhn_ok(digits: str) -> bool:
    """Luhn checksum — reduces false positives on random digit runs."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


@dataclass
class RedactResult:
    """Output of :func:`redact_pii`."""

    text: str
    redacted: bool


def redact_pii(text: str) -> RedactResult:
    """Redact card numbers, emails, and phone numbers before storage.

    Cards are redacted only when 13–16 digits *and* Luhn-valid; emails go before
    phones so an email's digits are never mistaken for a phone number.
    """
    redacted = False

    def _card_sub(match: re.Match[str]) -> str:
        nonlocal redacted
        digits = re.sub(r"\D", "", match.group())
        if len(digits) >= 13 and _luhn_ok(digits):
            redacted = True
            return CARD_TOKEN
        return match.group()

    result = _CARD_RE.sub(_card_sub, text)

    def _email_sub(_match: re.Match[str]) -> str:
        nonlocal redacted
        redacted = True
        return EMAIL_TOKEN

    result = _EMAIL_RE.sub(_email_sub, result)

    def _phone_sub(match: re.Match[str]) -> str:
        nonlocal redacted
        digits = re.sub(r"\D", "", match.group())
        if len(digits) >= 7:
            redacted = True
            return PHONE_TOKEN
        return match.group()

    result = _PHONE_RE.sub(_phone_sub, result)
    return RedactResult(text=result, redacted=redacted)


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

UNKNOWN_LANGUAGE = "unknown"


def detect_language(text: str) -> str:
    """Return an ISO 639-1 language code, or ``"unknown"``.

    Redaction tokens are stripped first so ``[REDACTED_EMAIL]`` etc. do not skew
    detection. Short/empty text reliably yields ``"unknown"``.
    """
    probe = re.sub(r"\[REDACTED_\w+\]", " ", text).strip()
    if len(probe.split()) < 2:
        return UNKNOWN_LANGUAGE
    try:
        return str(detect(probe))
    except LangDetectException:
        return UNKNOWN_LANGUAGE


# ---------------------------------------------------------------------------
# Normalisation & hashing for dedup
# ---------------------------------------------------------------------------


def normalise_text(text: str) -> str:
    """Canonicalise text for hashing: lowercase + whitespace-collapsed."""
    return re.sub(r"\s+", " ", text.strip().lower())


def content_hash(user_id: UUID, normalised_text: str) -> str:
    """Return a stable SHA-256 hex digest of ``user_id + normalised_text``.

    Scoping by ``user_id`` means identical text from different users is *not*
    treated as a duplicate.
    """
    payload = f"{user_id}\x00{normalised_text}".encode()
    return hashlib.sha256(payload).hexdigest()
