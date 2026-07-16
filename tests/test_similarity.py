from redline.similarity import PAIR_OVERLAP_THRESHOLD, similarity_score


def test_identical_text_scores_one():
    assert similarity_score("the quick fox", "the quick fox") == 1.0


def test_both_empty_scores_one():
    assert similarity_score("", "") == 1.0


def test_one_empty_scores_zero():
    assert similarity_score("something", "") == 0.0


def test_no_shared_words_scores_zero():
    assert similarity_score("alpha bravo", "charlie delta") == 0.0


def test_below_threshold_matches_plain_jaccard():
    # "the"/"quick" shared, "fox"/"dog" not: overlap = 2/3 (above 0.5), so
    # this is actually a below-vs-above sanity check via a lower-overlap
    # case instead. Use a pair with an overlap right at the boundary.
    a, b = "one two three four", "one five six seven"
    # shared={one}, union has 7 words -> jaccard = 1/7
    # overlap = 1/min(4,4) = 0.25, below PAIR_OVERLAP_THRESHOLD (0.5)
    assert similarity_score(a, b) == 1 / 7


def test_genuine_containment_scores_near_one():
    # Short unit fully contained in a longer, edited one -- the case
    # plain Jaccard under-scores (denominator penalizes size disparity).
    short = "the tenant shall maintain the property"
    long_ = "the tenant shall maintain the property and grounds in good repair"
    score = similarity_score(short, long_)
    assert score > 0.9  # near-total containment -> near 1.0, not ~0.19 Jaccard


def test_unrelated_short_text_does_not_get_false_positive_boost():
    # Control case from this session's empirical testing: two short,
    # generic, unrelated sentences can coincidentally share words, but
    # their overlap coefficient should stay at or below the threshold, so
    # the score must not get boosted toward 1.0.
    a, b = "the report is due", "the meeting is over"
    score = similarity_score(a, b)
    assert score < 0.5


def test_threshold_boundary_is_plain_jaccard():
    # At overlap == PAIR_OVERLAP_THRESHOLD exactly, score should equal
    # plain Jaccard (the "<=" branch), not yet ramped.
    a, b = "one two three four", "one two five six"
    # shared={one,two}, union=6 -> jaccard = 2/6 = 1/3
    # overlap = 2/min(4,4) = 0.5 == PAIR_OVERLAP_THRESHOLD
    assert similarity_score(a, b) == 1 / 3
