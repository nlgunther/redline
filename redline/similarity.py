"""Candidate-pairing similarity for Phase 1.

Threshold-gated blend of Jaccard overlap and the overlap coefficient
(Szymkiewicz-Simpson: |A intersect B| / min(|A|,|B|)). Plain Jaccard alone
systematically under-scores genuine containment -- a short unit fully
absorbed into a longer edited one can score well under 0.2 Jaccard even
though it's a perfect match modulo the extra text, because Jaccard's
denominator (the union) penalizes size disparity even under perfect
containment. The overlap coefficient fixes that but isn't safe alone: it
also scores short/generic unrelated text uncomfortably high, since two
short unrelated units can coincidentally share a large fraction of their
(small) word sets.

Design, verified empirically (see PLAN.md): below the containment
threshold `PAIR_OVERLAP_THRESHOLD`, overlap evidence is ignored entirely
and the score is plain Jaccard -- this is what protects against the
false-positive case. Above the threshold, the score ramps linearly from
Jaccard up to 1.0 as overlap approaches 1.0 (perfect containment).

This is the "practical default" flagged during design, not the fancier
background-corrected (document-frequency weighted) scoring discussed for
telling apart near-duplicate boilerplate clauses -- that's a documented
future enhancement (see docs/API.md), not required for v1. This score is
only ever used to decide which sub-units to pair for recursion; the actual
diff shown to the user always comes from difflib on the original
(un-lowercased) text, so lowercasing here doesn't hide anything -- see
text.py's normalize_case note.
"""

from .text import split_words

# Below this overlap coefficient, containment evidence is ignored and the
# score is plain Jaccard. Chosen from this session's measured cases: it
# keeps an unrelated-text control at pure Jaccard (0.133) while still
# fully crediting a genuine near-containment case (0.8 overlap) with a
# strong boost. Tune if real documents suggest a different cutoff.
PAIR_OVERLAP_THRESHOLD = 0.5


def similarity_score(a: str, b: str) -> float:
    """Word-set similarity for candidate pairing, case-insensitive
    (matching heuristic only). Blends Jaccard with the overlap
    coefficient above PAIR_OVERLAP_THRESHOLD so genuine containment (a
    short unit absorbed into a longer one) scores near 1.0 instead of
    being penalized by Jaccard's union-sized denominator.

    Examples:
        similarity_score("the quick fox", "the quick dog")  # -> 0.5 (no containment)
        similarity_score("the fox", "the quick brown fox jumps")  # -> boosted above plain Jaccard
    """
    words_a = set(w.lower() for w in split_words(a))
    words_b = set(w.lower() for w in split_words(b))
    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0

    intersection = len(words_a & words_b)
    j = intersection / len(words_a | words_b)
    overlap = intersection / min(len(words_a), len(words_b))
    if overlap <= PAIR_OVERLAP_THRESHOLD:
        return j
    weight = (overlap - PAIR_OVERLAP_THRESHOLD) / (1 - PAIR_OVERLAP_THRESHOLD)
    return j + weight * (1 - j)
