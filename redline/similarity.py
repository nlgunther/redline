"""Candidate-pairing similarity for Phase 1.

Plain Jaccard overlap on word sets. This is the "practical default" flagged
during design, not the fancier background-corrected (document-frequency
weighted) scoring discussed for telling apart near-duplicate boilerplate
clauses -- that's a documented future enhancement (see docs/API.md), not
required for v1. This score is only ever used to decide which sub-units to
pair for recursion; the actual diff shown to the user always comes from
difflib on the original (un-lowercased) text, so lowercasing here doesn't
hide anything -- see text.py's normalize_case note.
"""

from .text import split_words


def jaccard(a: str, b: str) -> float:
    """Word-set overlap, case-insensitive (matching heuristic only).

    Example:
        jaccard("the quick fox", "the quick dog")  # -> 0.5
    """
    words_a = set(w.lower() for w in split_words(a))
    words_b = set(w.lower() for w in split_words(b))
    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)
