"""Shared conflict resolution for order-preserving match sets.

Used by blocks.py (paragraph-level matches, whole document) and align.py
(sentence-level matches, within one hole) to resolve the same kind of
conflict the same way: two match candidates that would cross each other
(not increasing in both document positions) can't both be kept without
producing a non-monotonic alignment, so the longest mutually-consistent
subsequence is kept and the rest are demoted back to unmatched rather than
forcing a wrong pairing.
"""

import bisect


def resolve_order(matches: list[tuple]) -> tuple[list[tuple], list[tuple]]:
    """Keep the longest subsequence of matches that is strictly increasing
    in both document positions (patience-sorting LIS on the second
    position, after sorting by the first). Matches that would cross
    another kept match are dropped, not forced.

    Each match is a tuple whose first two elements are the two documents'
    positions (`(a_index, b_index, ...)`); any additional elements are
    carried through unchanged.

    Example:
        resolve_order([(0, 1), (1, 0)])
        # -> ([(1, 0)], [(0, 1)])  -- these cross, so only one is kept
    """
    matches = sorted(matches, key=lambda m: m[0])
    tails: list[int] = []
    tails_idx: list[int] = []
    predecessor = [-1] * len(matches)

    for k, (_, j, *_rest) in enumerate(matches):
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
