"""Phase 0: find paragraphs that are unchanged, or unchanged apart from a
known, cheap transformation (whitespace noise, then case).

Design assumption (confirmed with Ken): a "block" is at least a paragraph.
Paragraph boundaries come from document structure, not from discovering
block extents via a sliding window -- that removes the need for the
entropy-rate calibration explored earlier for word-level matching; there's
no minimum-length parameter to tune when the unit is already the natural,
structural paragraph.

Duplicate paragraphs within one document are rare at this granularity, so
matching defaults to a simple order-preserving assignment. When duplicates
do create a genuine conflict (matches that would cross each other), it's
resolved with the same longest-increasing-subsequence approach used for
anchor resolution in the design discussion, rather than guessing -- the
losing matches are demoted back to "unmatched" and handled by Phase 1
instead of forcing a wrong pairing.
"""

import bisect
from collections import defaultdict
from dataclasses import dataclass

from .hashing import light_hash
from .text import normalize_case, normalize_whitespace

# Strictest first. Each rung only searches paragraphs the previous rung
# left unmatched.
TRANSFORM_LADDER = (
    ("exact", lambda s: s),
    ("whitespace", normalize_whitespace),
    ("case", normalize_case),
)


@dataclass(frozen=True)
class Block:
    """A span already aligned between the two documents -- either truly
    identical or identical apart from `transform`. index_a/index_b are
    paragraph-index ranges. Both sides' raw text are kept (never the
    normalized form): "exact" and "whitespace" blocks render as unchanged
    (the difference is noise), but "case" blocks must still show a visible
    diff, so the renderer needs text_b too, not just text_a."""

    index_a: range
    index_b: range
    text_a: str
    text_b: str
    transform: str  # "exact" | "whitespace" | "case"


def find_blocks(
    paras_a: list[str], paras_b: list[str]
) -> tuple[list[Block], list[int], list[int]]:
    """Run the transform ladder and return (blocks, unmatched_a, unmatched_b).

    unmatched_a/unmatched_b are paragraph indices with no match at any
    ladder rung, plus any indices whose match was dropped to keep the
    overall assignment order-preserving. They are Phase 1's input.
    """
    remaining_a = list(enumerate(paras_a))
    remaining_b = list(enumerate(paras_b))
    all_matches: list[tuple[int, int, str]] = []

    for name, transform in TRANSFORM_LADDER:
        matched_a, matched_b, new_matches = _match_rung(
            paras_a, remaining_a, remaining_b, transform, name
        )
        all_matches.extend(new_matches)
        remaining_a = [x for x in remaining_a if x[0] not in matched_a]
        remaining_b = [x for x in remaining_b if x[0] not in matched_b]

    kept, dropped = _resolve_order(all_matches)
    blocks = _merge_adjacent(kept, paras_a, paras_b)

    unmatched_a = sorted({i for i, _ in remaining_a} | {i for i, _, _ in dropped})
    unmatched_b = sorted({j for j, _ in remaining_b} | {j for _, j, _ in dropped})
    return blocks, unmatched_a, unmatched_b


def _match_rung(paras_a, remaining_a, remaining_b, transform, name):
    """One ladder rung: hash remaining A paragraphs under `transform`,
    then greedily match each remaining B paragraph to the earliest
    unmatched A candidate with the same key, verifying true equality."""
    index: dict[bytes, list[int]] = defaultdict(list)
    for i, text in remaining_a:
        index[light_hash(transform(text))].append(i)

    matched_a: set[int] = set()
    matched_b: set[int] = set()
    new_matches: list[tuple[int, int, str]] = []
    for j, text_b in remaining_b:
        key = light_hash(transform(text_b))
        for i in index.get(key, ()):
            if i in matched_a:
                continue
            if transform(paras_a[i]) == transform(text_b):
                new_matches.append((i, j, name))
                matched_a.add(i)
                matched_b.add(j)
                break
    return matched_a, matched_b, new_matches


def _resolve_order(matches):
    """Keep the longest subsequence of matches that is strictly increasing
    in both document positions (patience-sorting LIS on the B-index,
    after sorting by A-index). Matches that would cross another kept
    match are dropped, not forced."""
    matches = sorted(matches, key=lambda m: m[0])
    tails: list[int] = []
    tails_idx: list[int] = []
    predecessor = [-1] * len(matches)

    for k, (_, j, _) in enumerate(matches):
        pos = bisect.bisect_left(tails, j)
        if pos == len(tails):
            tails.append(j)
            tails_idx.append(k)
        else:
            tails[pos] = j
            tails_idx[pos] = k
        predecessor[k] = tails_idx[pos - 1] if pos > 0 else -1

    kept_indices = []
    k = tails_idx[-1] if tails_idx else -1
    while k != -1:
        kept_indices.append(k)
        k = predecessor[k]
    kept_indices.reverse()

    kept_set = set(kept_indices)
    kept = [matches[k] for k in kept_indices]
    dropped = [m for idx, m in enumerate(matches) if idx not in kept_set]
    return kept, dropped


def _merge_adjacent(matches, paras_a, paras_b):
    """Combine consecutive same-transform matches into one Block, so a
    run of unchanged paragraphs becomes a single set-aside span."""
    blocks: list[Block] = []
    for i, j, name in matches:
        prev = blocks[-1] if blocks else None
        if (
            prev
            and prev.transform == name
            and prev.index_a.stop == i
            and prev.index_b.stop == j
        ):
            blocks[-1] = Block(
                index_a=range(prev.index_a.start, i + 1),
                index_b=range(prev.index_b.start, j + 1),
                text_a=prev.text_a + "\n\n" + paras_a[i],
                text_b=prev.text_b + "\n\n" + paras_b[j],
                transform=name,
            )
        else:
            blocks.append(Block(range(i, i + 1), range(j, j + 1), paras_a[i], paras_b[j], name))
    return blocks
