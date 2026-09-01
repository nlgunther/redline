"""Phase 1: recursive coarse-to-fine matching for the residual "holes"
Phase 0 couldn't resolve as unchanged.

A sentence pair that isn't byte-identical is diffed directly at word
granularity (_diff_op, one SequenceMatcher pass over both sides' word
tokens) -- see "2026-07-22" below for why there's no separate word-level
candidate-pairing step before that.

Reworked 2026-07-21 (see docs/JOURNAL_2026-07-21.md) to drop paragraph-
level pairing from this ladder entirely. The previous design paired
paragraphs first (one A-paragraph to one B-paragraph, via the DP below),
then recursed into sentences *within* that one pair. That silently
assumed the two documents agree on where paragraph breaks fall. They
don't have to: an author can split or merge a paragraph as part of an
edit, with no wording change to the sentences themselves. When that
happens, one side has N paragraph units for content the other side holds
in M != N units, and forcing a 1-to-1 paragraph pairing has no correct
answer -- whichever single partner "wins" the DP, the rest renders as a
disconnected insert+delete even though most of the sentences involved are
identical (see the real case this was found from, main-15 vs main-14a: a
single old paragraph held two sentences an author later split apart with
a blank line, and the *unchanged* second sentence rendered as a full
delete alongside the reworded first one).

Fix: paragraph structure is no longer a matching boundary at all. Phase 1
now flattens both sides' paragraphs to a single, tagged sentence sequence
(align_paragraphs/_flatten_to_sentences) and aligns sentences directly
across the whole hole -- a paragraph split or merge just becomes "the
same sentence, tagged with a different paragraph index on each side",
which flows through the existing identity-first machinery in align_units
without any special-casing. Paragraph boundaries are kept purely as
metadata on each resulting item and used only afterward, by
_group_by_paragraph, to regroup sentence-level ops back into rendered
paragraphs -- following the *new* document's paragraph structure, the
same convention track-changes tools use (see _group_by_paragraph's
docstring for the one exception: a wholly-deleted paragraph, which has no
new-side position, groups by the *old* document's structure instead so it
still renders as its own block).

Assumption (flagged, not blocking): candidate sentence pairing within a
hole uses a small O(n*m) alignment DP scored by similarity_score() (see
similarity.py), since n and m here are the units inside one hole (now
sentences across every paragraph in the hole, not just within one already-
matched paragraph pair -- still a handful of units, not the whole
document). Phase 0's block ordering already did the expensive whole-
document assignment. If a hole turns out to be huge in practice, this DP
is the place to revisit. The DP is skipped entirely for the 1-vs-1 case
(see _align_sequence).

2026-07-21, later the same day: added an exact-match pre-pass ahead of the DP above (see
_exact_match_sentences/_align_flattened_sentences). _align_sequence's DP
is order-preserving, so two sentences that are identical but sit in a
different relative order on each side (a local reorder within one hole)
could still lose to a same-order-but-wrong pairing -- the DP has no way
to represent the crossing correspondence a true reorder needs. Mirrors
Phase 0's own fix for the equivalent paragraph-level problem: hash every
sentence for an exact, position-independent match first, resolve which
candidates can coexist without crossing (same resolve_order() used by
blocks.py), and only hand whatever's left to the DP. See
docs/JOURNAL_2026-07-21.md for the worked example and the reasoning that
led here.

2026-07-22: removed the word-level candidate-pairing step entirely.
align_units used to have a third tier below "sentence not good enough as
one edit": split both sides into individual words and run the *same*
DP-based pairing used for sentences (_align_sequence, scored by
similarity_score) to decide which words to diff together before falling
back to _diff_op. That scorer treats its arguments as word sets, so
comparing two single words degenerates to "identical or score zero" --
any two non-identical words are unlinkable candidates, so a run of
several changed words shattered into one Delete/Insert per word instead
of a single coherent replace span (64 ops instead of 1, in a real
example). _diff_op already produces a clean multi-word replace span via
its own SequenceMatcher pass -- there was nothing for word-level DP
pairing to usefully decide once a sentence wasn't good enough as a
single edit, so align_units now calls _diff_op directly in that case
too, same as it always did once at the (former) word floor. See
docs/JOURNAL_2026-07-22.md for the worked example and what this made
structurally dead (GRANULARITY_LADDER, GOOD_ENOUGH, MIN_TOKENS,
_at_floor, _clears_threshold, _split, _interleave -- all removed).
"""

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher

from .hashing import light_hash
from .ordering import resolve_order
from .similarity import similarity_score
from .text import split_sentences, split_words

PAIR_THRESHOLD = 0.15  # minimum similarity score to accept a candidate pairing


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


@dataclass(frozen=True)
class ParagraphGroup:
    """One rendered paragraph's worth of sentence-level ops (Identity/
    Edit/Insert/Delete). Added with the 2026-07-21 sentence-flattening
    rework: matching now happens purely at sentence granularity (see the
    module docstring), so paragraph boundaries are just metadata used to
    regroup the resulting ops back into paragraph-shaped output --
    see _group_by_paragraph. render.py renders one ParagraphGroup as a
    single <p> (or <hN> for a heading, via style_by_text)."""

    items: list


@dataclass(frozen=True)
class _TaggedSentence:
    """A sentence plus the index of the paragraph (within this hole's
    paras_a/paras_b) it came from -- the only place paragraph structure
    survives past _flatten_to_sentences, kept solely so _group_by_paragraph
    can reconstruct it afterward."""

    text: str
    para_index: int


def align_paragraphs(paras_a: list[str], paras_b: list[str]) -> list[ParagraphGroup]:
    """Entry point for Phase 1: align one hole's content at sentence
    granularity, ignoring which paragraph each sentence started in, then
    regroup into rendered paragraphs. See the module docstring for why
    paragraph-level pairing was dropped.

    Example:
        # old: one paragraph holding two sentences; new: same two
        # sentences split into two paragraphs, with the first reworded.
        align_paragraphs(
            ["Shared opening sentence. Shared closing sentence."],
            ["Shared opening sentence, reworded.", "Shared closing sentence."],
        )
        # -> [ParagraphGroup([Edit(...)]), ParagraphGroup([Identity("Shared closing sentence.")])]
        # -- the closing sentence is recognized as unchanged even though
        # it moved to a different paragraph than its old one.
    """
    if not paras_a and not paras_b:
        return []
    sents_a = _flatten_to_sentences(paras_a)
    sents_b = _flatten_to_sentences(paras_b)
    tagged_ops = _align_flattened_sentences(sents_a, sents_b)
    return _group_by_paragraph(tagged_ops)


def _flatten_to_sentences(paras: list[str]) -> list[_TaggedSentence]:
    return [
        _TaggedSentence(sentence, p_idx)
        for p_idx, para in enumerate(paras)
        for sentence in split_sentences(para)
    ]


def _align_flattened_sentences(sents_a, sents_b) -> list[tuple]:
    """Match one hole's flattened sentences in two stages: an exact,
    position-independent hash pass first, then the fuzzy order-preserving
    DP (_align_sequence) over whatever the hash pass didn't claim.

    A hash match and a DP match can genuinely cross each other in
    original-index terms -- that IS what a local sentence reorder is, by
    definition -- so they can't be merged into one pairs list and handed
    to _interleave_tagged's single monotonic walk (tried this first; it
    silently re-dropped the exact match that made the swap case work at
    all -- see docs/JOURNAL_2026-07-21.md). Instead the two are resolved
    independently -- anchors become Identity directly, the residual runs
    through the existing, self-contained _align_sequence/_interleave_tagged
    exactly as before -- and only their *rendered ops* are merged
    afterward, by _merge_in_paragraph_order.
    """
    exact_candidates = _exact_match_sentences(sents_a, sents_b)
    anchor_pairs, _ = resolve_order(exact_candidates)
    matched_a = {i for i, _ in anchor_pairs}
    matched_b = {j for _, j in anchor_pairs}

    residual_a = [s for i, s in enumerate(sents_a) if i not in matched_a]
    residual_b = [s for j, s in enumerate(sents_b) if j not in matched_b]
    texts_a = [s.text for s in residual_a]
    texts_b = [s.text for s in residual_b]
    pairs, unmatched_a, unmatched_b = _align_sequence(texts_a, texts_b)
    residual_ops = _interleave_tagged(residual_a, residual_b, pairs, unmatched_a, unmatched_b)

    anchor_ops = [
        (Identity(sents_a[i].text), (sents_a[i].para_index, sents_b[j].para_index))
        for i, j in anchor_pairs
    ]
    return _merge_in_paragraph_order(anchor_ops, residual_ops)


def _merge_in_paragraph_order(anchor_ops: list[tuple], residual_ops: list[tuple]) -> list[tuple]:
    """Combine exact-match anchor ops and fuzzy residual ops into one
    list ordered for _group_by_paragraph.

    A genuine reorder has no single correct fine-grained sentence order
    (that's what makes it a reorder) -- what correctness actually
    requires is that every sentence sharing a rendered paragraph stays
    contiguous, not any particular order within it. A stable sort by
    new-document paragraph index (old-document index as fallback for
    pure deletions, which have no new-side paragraph) guarantees the
    former without needing to resolve the latter -- consistent with
    _group_by_paragraph's own already-documented tolerance for not
    fully reordering same-paragraph groups relative to each other.
    """
    combined = anchor_ops + residual_ops
    combined.sort(key=lambda t: (0, t[1][1]) if t[1][1] is not None else (1, t[1][0]))
    return combined


def _exact_match_sentences(sents_a: list[_TaggedSentence], sents_b: list[_TaggedSentence]):
    """Hash every sentence and match by exact text, regardless of
    position -- mirrors blocks.py's own exact-match rung (_match_rung),
    one granularity level down. A sentence that's simply been reordered
    relative to its counterpart is found here just as readily as one
    that hasn't moved at all; resolve_order() (called by the caller)
    decides separately whether a given match can be kept without
    crossing another one.

    Example:
        _exact_match_sentences(
            [_TaggedSentence("Alpha.", 0), _TaggedSentence("Beta.", 0)],
            [_TaggedSentence("Beta.", 0), _TaggedSentence("Alpha.", 0)],
        )
        # -> [(0, 1), (1, 0)]  -- both found, regardless of order
    """
    index: dict[bytes, list[int]] = defaultdict(list)
    for i, s in enumerate(sents_a):
        index[light_hash(s.text)].append(i)

    matched_a: set[int] = set()
    matches: list[tuple[int, int]] = []
    for j, s in enumerate(sents_b):
        for i in index.get(light_hash(s.text), ()):
            if i not in matched_a and sents_a[i].text == s.text:
                matches.append((i, j))
                matched_a.add(i)
                break
    return matches


def _interleave_tagged(sents_a, sents_b, pairs, unmatched_a, unmatched_b) -> list[tuple]:
    """Like _interleave (below), but for the top-level sentence alignment
    across a whole hole: walks matched pairs and gaps in document order
    (same logic), and tags each resulting item with (old_paragraph_index,
    new_paragraph_index) -- None on whichever side didn't contribute --
    so _group_by_paragraph can reconstruct rendered paragraphs afterward.
    """
    tagged: list[tuple] = []
    ua, ub = set(unmatched_a), set(unmatched_b)
    last_i, last_j = -1, -1
    for i, j in pairs + [(len(sents_a), len(sents_b))]:
        for k in range(last_i + 1, i):
            if k in ua:
                tagged.append((Delete(sents_a[k].text), (sents_a[k].para_index, None)))
        for k in range(last_j + 1, j):
            if k in ub:
                tagged.append((Insert(sents_b[k].text), (None, sents_b[k].para_index)))
        if i < len(sents_a):
            tag = (sents_a[i].para_index, sents_b[j].para_index)
            for item in align_units(sents_a[i].text, sents_b[j].text, "sentence"):
                tagged.append((item, tag))
        last_i, last_j = i, j
    return tagged


def _group_by_paragraph(tagged_ops: list[tuple]) -> list[ParagraphGroup]:
    """Regroup flattened, tagged sentence-level ops back into rendered
    paragraphs. An item with a new-document paragraph index groups with
    its neighbors by that index, so the output follows the *new*
    document's paragraph structure (the same convention track-changes
    tools use: show the result as it will look once changes are
    accepted). A run of purely deleted sentences -- no new-side paragraph
    at all -- groups by the *old*-document paragraph index instead, so a
    wholly-removed paragraph still renders as its own block rather than
    bleeding into whichever kept paragraph happens to be adjacent.
    """
    groups: list[ParagraphGroup] = []
    current_key = None
    current_items: list = []
    for item, (a_idx, b_idx) in tagged_ops:
        key = ("new", b_idx) if b_idx is not None else ("old", a_idx)
        if key != current_key and current_items:
            groups.append(ParagraphGroup(current_items))
            current_items = []
        current_key = key
        current_items.append(item)
    if current_items:
        groups.append(ParagraphGroup(current_items))
    return groups


def align_units(text_a: str, text_b: str, level: str = "sentence") -> list:
    """Align a single pair of units (a sentence, or a paragraph-sized
    Block that needs a visible diff -- see render._render_block).

    `level` is accepted for call-site compatibility (existing callers
    pass "sentence" or "word") but no longer changes behavior -- see the
    module docstring's "2026-07-22" entry for why the word-level
    candidate-pairing tier this used to gate was removed rather than
    fixed in place.
    """
    if text_a == text_b:
        return [Identity(text_a)] if text_a else []
    tokens_a, tokens_b = split_words(text_a), split_words(text_b)
    return _diff_op(text_a, text_b, tokens_a, tokens_b)


def _diff_op(text_a, text_b, tokens_a, tokens_b) -> list:
    if not tokens_a and not tokens_b:
        return []
    if not tokens_a:
        return [Insert(text_b)]
    if not tokens_b:
        return [Delete(text_a)]
    opcodes = tuple(SequenceMatcher(None, tokens_a, tokens_b, autojunk=False).get_opcodes())
    return [Edit(text_a, text_b, tuple(tokens_a), tuple(tokens_b), opcodes)]


def _align_sequence(units_a: list[str], units_b: list[str]):
    """Needleman-Wunsch-style global alignment maximizing total similarity
    score, allowing any unit to go unmatched at zero cost. O(n*m), which
    is cheap for the small unit counts inside one hole.

    Special case: when each side has exactly one unit, there is no
    pairing decision to make -- they're the only candidates for each
    other, so pair them unconditionally rather than gating through
    PAIR_THRESHOLD. Without this, two totally dissimilar sole occupants
    of a hole render as a disconnected Delete+Insert instead of one
    Edit, even though "being the only candidate on each side" is by
    itself sufficient justification to pair them.
    """
    if len(units_a) == 1 and len(units_b) == 1:
        return [(0, 0)], [], []
    scores = _dp_scores(units_a, units_b)
    return _traceback(units_a, units_b, scores)


def _dp_scores(units_a, units_b):
    n, m = len(units_a), len(units_b)
    scores = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            match = scores[i - 1][j - 1] + similarity_score(units_a[i - 1], units_b[j - 1])
            scores[i][j] = max(match, scores[i - 1][j], scores[i][j - 1])
    return scores


def _traceback(units_a, units_b, scores):
    i, j = len(units_a), len(units_b)
    pairs = []
    while i > 0 and j > 0:
        pair_score = similarity_score(units_a[i - 1], units_b[j - 1])
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
