from redline.blocks import find_blocks


def test_exact_duplicate_paragraph_found():
    a = ["Same paragraph.", "Different one."]
    b = ["Same paragraph.", "Changed one."]
    blocks, ua, ub = find_blocks(a, b)
    assert len(blocks) == 1
    assert blocks[0].transform == "exact"
    assert blocks[0].text_a == "Same paragraph."
    assert ua == [1] and ub == [1]


def test_whitespace_only_change_classified():
    a = ["Party  A's   claim."]
    b = ["Party A's claim."]
    blocks, ua, ub = find_blocks(a, b)
    assert len(blocks) == 1
    assert blocks[0].transform == "whitespace"


def test_case_only_change_classified_not_hidden():
    a = ["The Agreement is binding."]
    b = ["The agreement is binding."]
    blocks, ua, ub = find_blocks(a, b)
    assert len(blocks) == 1
    assert blocks[0].transform == "case"
    assert blocks[0].text_a == "The Agreement is binding."
    assert blocks[0].text_b == "The agreement is binding."


def test_adjacent_matches_merge_into_one_block():
    a = ["Para one.", "Para two.", "Para three."]
    b = ["Para one.", "Para two.", "Para three."]
    blocks, ua, ub = find_blocks(a, b)
    assert len(blocks) == 1
    assert blocks[0].index_a == range(0, 3)
    assert blocks[0].index_b == range(0, 3)


def test_completely_different_documents_no_blocks():
    a = ["Alpha content here."]
    b = ["Totally unrelated text."]
    blocks, ua, ub = find_blocks(a, b)
    assert blocks == []
    assert ua == [0] and ub == [0]


def test_moved_block_does_not_crash_and_preserves_order():
    a = ["Alpha clause.", "Bravo clause.", "Charlie clause."]
    b = ["Bravo clause.", "Alpha clause.", "Charlie clause."]
    blocks, ua, ub = find_blocks(a, b)
    # Bravo and Charlie can both match without crossing; Alpha's match
    # would cross Bravo's, so it's dropped back to unmatched rather than
    # forcing an inconsistent (crossing) alignment.
    assert all(
        blocks[i].index_a.start < blocks[i + 1].index_a.start
        and blocks[i].index_b.start < blocks[i + 1].index_b.start
        for i in range(len(blocks) - 1)
    )
    assert 0 in ua  # Alpha's A-index ends up unmatched
    assert 0 in ub or 1 in ub  # Alpha's B-index ends up unmatched


def test_duplicate_paragraph_pairs_by_position_order():
    a = ["Boilerplate.", "Middle.", "Boilerplate."]
    b = ["Boilerplate.", "Different middle.", "Boilerplate."]
    blocks, ua, ub = find_blocks(a, b)
    exact_blocks = [b_ for b_ in blocks if b_.transform == "exact"]
    assert len(exact_blocks) == 2
    assert exact_blocks[0].index_a.start < exact_blocks[1].index_a.start
    assert exact_blocks[0].index_b.start < exact_blocks[1].index_b.start
