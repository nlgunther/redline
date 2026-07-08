"""Text normalization and splitting.

Two things are deliberately kept separate throughout this package: the
*raw* text (what gets rendered) and a *normalized* key (what gets compared
or hashed). Normalization here only removes incidental typographic noise
(whitespace, smart quotes) -- it never folds case. A case-only change can
be legally meaningful (a defined term vs. a generic word), so it must
still show up in the output; see blocks.py's transform ladder for how
case changes are still found cheaply without being hidden.
"""

import re
import unicodedata

_QUOTE_MAP = str.maketrans({
    "“": '"', "”": '"', "‘": "'", "’": "'",
    " ": " ",  # non-breaking space
})
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"\S+")
# Split after sentence-ending punctuation followed by whitespace and a
# capital letter, digit, quote, or opening paren. Doesn't special-case
# abbreviations (Mr., etc.) -- acceptable for v1, see docs/API.md.
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(\"'])")


def normalize_whitespace(text: str) -> str:
    """Collapse incidental typographic noise. Does not fold case.

    Example:
        normalize_whitespace("Party  A’s  claim")
        # -> "Party A's claim"
    """
    text = unicodedata.normalize("NFC", text)
    text = text.translate(_QUOTE_MAP)
    return _WHITESPACE_RE.sub(" ", text).strip()


def normalize_case(text: str) -> str:
    """Whitespace-normalize, then fold case. Used only as a matching key
    (see blocks.py) -- never used for rendered output."""
    return normalize_whitespace(text).lower()


def split_paragraphs(text: str) -> list[str]:
    """Split plain text into paragraphs on blank lines."""
    paras = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in paras if p.strip()]


def split_sentences(text: str) -> list[str]:
    """Split a paragraph into sentences with a lightweight regex splitter.

    Example:
        split_sentences("Pay by May 1. Late fees apply after that.")
        # -> ["Pay by May 1.", "Late fees apply after that."]
    """
    text = text.strip()
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


def split_words(text: str) -> list[str]:
    """Split on whitespace into word tokens (punctuation stays attached)."""
    return _WORD_RE.findall(text)
