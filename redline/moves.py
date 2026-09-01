"""Phase 2: find sentences that relocated across Phase 1 hole boundaries.

Phase 0 (blocks.py) and Phase 1 (align.py) each look for a match within
their own scope -- Phase 0 across the whole document at paragraph
granularity, Phase 1 within one hole at sentence granularity. Content
that moved far enough to land in a *different* hole than its counterpart
is invisible to both: each hole is matched independently, so a sentence
that's simply relocated (not reworded) survives as a plain, unmatched
Delete on one side and a plain, unmatched Insert on the other, with
nothing connecting them.

This pass runs once, after pipeline._stitch has assembled the whole
document's Block/ParagraphGroup sequence, and looks for exact-text
matches between every orphaned Delete and every orphaned Insert across
the *entire* document -- mirroring blocks.py's own whole-document,
hash-based approach, just applied to Phase 1's leftovers instead of the
original paragraphs. A match found here is replaced with a MovedAway/
MovedHere marker pair instead of rendering as an unrelated delete+insert.

Unlike blocks.py's paragraph matching or align.py's local reorder fix,
no LIS/resolve_order conflict resolution is needed: those exist because
their matches feed a monotonic gap-filling walk (_interleave/
_interleave_tagged), which requires non-crossing pairs to compute
correctly. This pass instead splices into an already-finalized rendering
order -- it never needs "is this pairing consistent with the others,"
only "does this Delete's text exactly match some Insert's text" -- so a
simple greedy match (each Delete claims the earliest still-unclaimed
Insert with equal text) is sufficient. Content left ambiguous (e.g. more
occurrences of some boilerplate sentence on one side than the other)
just stays a plain Delete/Insert, same demote-don't-force policy used
everywhere else in this codebase.

Only whole-sentence Delete/Insert ops are candidates -- word-level ins/
del *inside* an Edit are not visible at this granularity, correctly out
of scope (a partially-reworded sentence didn't "move").
"""

from dataclasses import dataclass

from .align import Delete, Insert, ParagraphGroup
from .hashing import light_hash


@dataclass(frozen=True)
class MovedAway:
    """A sentence's old position, once its exact match has been found
    elsewhere in the document as a MovedHere. Rendered as a short
    direction marker, not the full text -- the full text is shown once,
    at the MovedHere location, matching the "show the result as it will
    look once changes are accepted" convention align._group_by_paragraph
    already uses for ordinary content.

    direction: "above" | "below" -- where the MovedHere counterpart sits
    relative to this marker, in rendered document order.
    """

    text: str
    direction: str


@dataclass(frozen=True)
class MovedHere:
    """The new position of a sentence whose old position is now a
    MovedAway marker elsewhere in the document.

    direction: "above" | "below" -- where the MovedAway counterpart sits
    relative to this item, in rendered document order.
    """

    text: str
    direction: str


def detect_moves(items: list) -> list:
    """Find exact-content Delete/Insert pairs that survived Phase 0 and
    Phase 1 unmatched only because they're not in the same hole, and
    replace them with MovedAway/MovedHere markers. Returns a new list;
    `items` (and any ParagraphGroup within it) is not mutated.

    Example:
        items = [
            ParagraphGroup([Delete("Charlie paragraph moved to the end.")]),
            Block(...),  # "Alpha paragraph unchanged." -- the sole anchor
            ParagraphGroup([Edit(...)]),  # "Bravo paragraph ... reworded."
            ParagraphGroup([Insert("Charlie paragraph moved to the end.")]),
        ]
        detect_moves(items)
        # -> Charlie's Delete becomes MovedAway(..., "below"); its
        # Insert becomes MovedHere(..., "above")
    """
    deletes = _collect(items, Delete)
    inserts = _collect(items, Insert)

    index: dict[bytes, list[int]] = {}
    for pos, (_, _, op) in enumerate(inserts):
        index.setdefault(light_hash(op.text), []).append(pos)

    claimed: set[int] = set()
    matches: list[tuple[tuple, tuple]] = []
    for d_ref in deletes:
        _, _, d_op = d_ref
        for pos in index.get(light_hash(d_op.text), ()):
            if pos in claimed:
                continue
            i_ref = inserts[pos]
            if i_ref[2].text == d_op.text:
                matches.append((d_ref, i_ref))
                claimed.add(pos)
                break

    if not matches:
        return items

    replacements: dict[tuple[int, int], object] = {}
    for (d_group, d_pos, d_op), (i_group, i_pos, i_op) in matches:
        away_direction = "below" if d_group < i_group else "above"
        here_direction = "above" if d_group < i_group else "below"
        replacements[(d_group, d_pos)] = MovedAway(d_op.text, away_direction)
        replacements[(i_group, i_pos)] = MovedHere(i_op.text, here_direction)

    return _apply(items, replacements)


def _collect(items: list, op_type: type) -> list[tuple]:
    """Every (item_index_in_items, position_in_group.items, op) for a
    given op type. Block items (Phase 0 anchors) never contain Delete/
    Insert by construction, so only ParagraphGroups are scanned."""
    found = []
    for group_idx, item in enumerate(items):
        if not isinstance(item, ParagraphGroup):
            continue
        for item_idx, op in enumerate(item.items):
            if isinstance(op, op_type):
                found.append((group_idx, item_idx, op))
    return found


def _apply(items: list, replacements: dict) -> list:
    new_items = []
    for group_idx, item in enumerate(items):
        if not isinstance(item, ParagraphGroup):
            new_items.append(item)
            continue
        new_ops = [
            replacements.get((group_idx, item_idx), op)
            for item_idx, op in enumerate(item.items)
        ]
        new_items.append(ParagraphGroup(new_ops))
    return new_items
