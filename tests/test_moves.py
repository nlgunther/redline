from redline.align import Delete, Edit, Identity, Insert, ParagraphGroup
from redline.blocks import Block
from redline.moves import MovedAway, MovedHere, detect_moves


def _kinds(items):
    return [
        [type(op).__name__ for op in item.items] if isinstance(item, ParagraphGroup) else type(item).__name__
        for item in items
    ]


def test_relocated_sentence_in_different_holes_becomes_a_moved_pair():
    # Charlie's Delete (before the Alpha anchor) and Insert (after it) sit
    # in two different holes -- align_paragraphs never sees them together,
    # so this is exactly the case Phase 1 can't catch on its own.
    items = [
        ParagraphGroup([Delete("Charlie paragraph moved to the end.")]),
        Block(range(0, 1), range(0, 1), "Alpha paragraph unchanged.", "Alpha paragraph unchanged.", "exact"),
        ParagraphGroup([Insert("Charlie paragraph moved to the end.")]),
    ]

    result = detect_moves(items)

    away = result[0].items[0]
    here = result[2].items[0]
    assert isinstance(away, MovedAway) and away.text == "Charlie paragraph moved to the end."
    assert isinstance(here, MovedHere) and here.text == "Charlie paragraph moved to the end."
    assert away.direction == "below"
    assert here.direction == "above"


def test_no_matching_orphan_leaves_items_untouched():
    items = [ParagraphGroup([Delete("Nothing matches this.")]), ParagraphGroup([Insert("Unrelated new text.")])]
    result = detect_moves(items)
    assert _kinds(result) == [["Delete"], ["Insert"]]


def test_unrelated_ops_in_the_same_groups_are_left_alone():
    # A moved sentence alongside genuinely new/changed/unchanged content in
    # the same paragraphs -- only the matching pair should be touched.
    items = [
        ParagraphGroup([Delete("Moved sentence here."), Identity("Kept sentence.")]),
        ParagraphGroup([
            Identity("Kept sentence."),
            Edit("Old wording.", "New wording.", ("Old", "wording."), ("New", "wording."),
                 (("replace", 0, 1, 0, 1), ("equal", 1, 2, 1, 2))),
            Insert("Moved sentence here."),
        ]),
    ]

    result = detect_moves(items)

    assert isinstance(result[0].items[0], MovedAway)
    assert result[0].items[1] == Identity("Kept sentence.")
    assert result[1].items[0] == Identity("Kept sentence.")
    assert isinstance(result[1].items[1], Edit)
    assert isinstance(result[1].items[2], MovedHere)


def test_content_moved_backward_is_marked_with_the_opposite_direction():
    # The mirror image of the main case: new position comes *before* the
    # old one in rendered order.
    items = [
        ParagraphGroup([Insert("Early content, later in the old document.")]),
        Block(range(0, 1), range(0, 1), "Anchor.", "Anchor.", "exact"),
        ParagraphGroup([Delete("Early content, later in the old document.")]),
    ]

    result = detect_moves(items)

    here = result[0].items[0]
    away = result[2].items[0]
    assert isinstance(here, MovedHere) and here.direction == "below"
    assert isinstance(away, MovedAway) and away.direction == "above"


def test_duplicate_orphan_content_matches_greedily_without_crashing():
    # Two identical deleted sentences, only one matching insert -- the
    # ambiguous second one should stay a plain Delete, not crash or
    # double-claim the same Insert.
    items = [
        ParagraphGroup([Delete("Repeated boilerplate line.")]),
        ParagraphGroup([Delete("Repeated boilerplate line.")]),
        ParagraphGroup([Insert("Repeated boilerplate line.")]),
    ]

    result = detect_moves(items)

    kinds = [type(op).__name__ for group in result for op in group.items]
    assert kinds.count("MovedAway") == 1
    assert kinds.count("Delete") == 1
    assert kinds.count("MovedHere") == 1


def test_empty_items_returns_empty():
    assert detect_moves([]) == []
