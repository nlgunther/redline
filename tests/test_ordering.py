from redline.ordering import resolve_order


def test_non_crossing_matches_are_all_kept():
    kept, dropped = resolve_order([(0, 0), (1, 1), (2, 2)])
    assert kept == [(0, 0), (1, 1), (2, 2)]
    assert dropped == []


def test_crossing_pair_drops_one_keeps_the_other():
    kept, dropped = resolve_order([(0, 1), (1, 0)])
    assert len(kept) == 1
    assert len(dropped) == 1
    assert set(kept) | set(dropped) == {(0, 1), (1, 0)}


def test_extra_payload_elements_are_carried_through():
    # blocks.py's matches carry a transform name as a third element;
    # resolve_order only looks at the first two positions for ordering.
    kept, dropped = resolve_order([(0, 0, "exact"), (1, 1, "case")])
    assert kept == [(0, 0, "exact"), (1, 1, "case")]


def test_empty_input_returns_empty():
    assert resolve_order([]) == ([], [])
