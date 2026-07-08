"""Phase 1: recursive coarse-to-fine matching for the residual "holes"
Phase 0 couldn't resolve as unchanged.

Granularity ladder: paragraph -> sentence -> word. At each level, a pair
of units is either accepted as a legible diff (difflib's own ratio is the
stopping test -- see _clears_threshold) or, if not good enough and still
splittable, broken into the next level's units and re-aligned. Rejected
pairs at a given level become plain insertions/deletions rather than being
forced together -- see _align_sequence.

Assumption (flagged, not blocking): candidate pairing within a hole uses
a small O(n*m) alignment DP scored by Jaccard overlap, since n and m here
are the units inside one hole (a handful of paragraphs/sentences), not the
whole document -- Phase 0's block ordering already did the expensive
whole-document assignment. If a hole turns out to be huge in practice,
this DP is the place to revisit.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher

from .similarity import jaccard
from .text import split_sentences, split_words

GRANULARITY_LADDER = ["paragraph", "sentence", "word"]
GOOD_ENOUGH = {"paragraph": 0.35, "sentence": 0.55}
MIN_TOKENS = 6
PAIR_THRESHOLD = 0.15  # minimum Jaccard score to accept a candidate pairing


@dataclass(frozen=True)
class Identity:
    text: str


@dataclass(frozen=True)
class Edit:
    text_a: str
    text_b: str
    tokens_a: tuple
    tokens_b: tuple
    opcodes: tuple


@dataclass(frozen=True)
class Insert:
    text: str


@dataclass(frozen=True)
class Delete:
    text: str


def align_paragraphs(paras_a: list[str], paras_b: list[str]) -> list:
    """Entry point for Phase 1: align the paragraph contents of one hole."""
    if not paras_a and not paras_b:
        return []
    pairs, unmatched_a, unmatched_b = _align_sequence(paras_a, paras_b)
    return _interleave(paras_a, paras_b, pairs, unmatched_a, unmatched_b, "paragraph")


def align_units(text_a: str, text_b: str, level: str) -> list:
    """Align a single pair of units (one paragraph, one sentence, ...)."""
    if text_a == text_b:
        return [Identity(text_a)] if text_a else []

    tokens_a, tokens_b = split_words(text_a), split_words(text_b)
    if _at_floor(level, tokens_a, tokens_b):
        return _diff_op(text_a, text_b, tokens_a, tokens_b)

    sm = SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)
    if _clears_threshold(sm, GOOD_ENOUGH[level]):
        return _diff_op(text_a, text_b, tokens_a, tokens_b)

    next_level = GRANULARITY_LADDER[GRANULARITY_LADDER.index(level) + 1]
    units_a, units_b = _split(text_a, next_level), _split(text_b, next_level)
    pairs, unmatched_a, unmatched_b = _align_sequence(units_a, units_b)
    return _interleave(units_a, units_b, pairs, unmatched_a, unmatched_b, next_level)


def _at_floor(level, tokens_a, tokens_b) -> bool:
    return level == "word" or len(tokens_a) < MIN_TOKENS or len(tokens_b) < MIN_TOKENS


def _clears_threshold(sm: SequenceMatcher, threshold: float) -> bool:
    """Staged cheap-to-expensive check using difflib's own upper bounds,
    so the full O(n*m) alignment only runs when it might matter."""
    if sm.real_quick_ratio() < threshold:
        return False
    if sm.quick_ratio() < threshold:
        return False
    return sm.ratio() >= threshold


def _diff_op(text_a, text_b, tokens_a, tokens_b) -> list:
    if not tokens_a and not tokens_b:
        return []
    if not tokens_a:
        return [Insert(text_b)]
    if not tokens_b:
        return [Delete(text_a)]
    opcodes = tuple(SequenceMatcher(None, tokens_a, tokens_b, autojunk=False).get_opcodes())
    return [Edit(text_a, text_b, tuple(tokens_a), tuple(tokens_b), opcodes)]


def _split(text, level) -> list[str]:
    if level == "sentence":
        return split_sentences(text)
    if level == "word":
        return split_words(text)
    raise ValueError(f"cannot split below word level (got {level!r})")


def _align_sequence(units_a: list[str], units_b: list[str]):
    """Needleman-Wunsch-style global alignment maximizing total Jaccard
    score, allowing any unit to go unmatched at zero cost. O(n*m), which
    is cheap for the small unit counts inside one hole."""
    scores = _dp_scores(units_a, units_b)
    return _traceback(units_a, units_b, scores)


def _dp_scores(units_a, units_b):
    n, m = len(units_a), len(units_b)
    scores = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            match = scores[i - 1][j - 1] + jaccard(units_a[i - 1], units_b[j - 1])
            scores[i][j] = max(match, scores[i - 1][j], scores[i][j - 1])
    return scores


def _traceback(units_a, units_b, scores):
    i, j = len(units_a), len(units_b)
    pairs = []
    while i > 0 and j > 0:
        pair_score = jaccard(units_a[i - 1], units_b[j - 1])
        if scores[i][j] == scores[i - 1][j - 1] + pair_score and pair_score >= PAIR_THRESHOLD:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif scores[i][j] == scores[i - 1][j]:
            i -= 1
        else:
            j -= 1
    pairs.reverse()
    matched_a = {i for i, _ in pairs}
    matched_b = {j for _, j in pairs}
    unmatched_a = [i for i in range(len(units_a)) if i not in matched_a]
    unmatched_b = [j for j in range(len(units_b)) if j not in matched_b]
    return pairs, unmatched_a, unmatched_b


def _interleave(units_a, units_b, pairs, unmatched_a, unmatched_b, level) -> list:
    """Walk matched pairs in document order; unmatched units in the gaps
    become deletions (from A) then insertions (from B) in place."""
    ops = []
    ua, ub = set(unmatched_a), set(unmatched_b)
    last_i, last_j = -1, -1
    for i, j in pairs + [(len(units_a), len(units_b))]:
        for k in range(last_i + 1, i):
            if k in ua:
                ops.append(Delete(units_a[k]))
        for k in range(last_j + 1, j):
            if k in ub:
                ops.append(Insert(units_b[k]))
        if i < len(units_a):
            ops.extend(align_units(units_a[i], units_b[j], level))
        last_i, last_j = i, j
    return ops
