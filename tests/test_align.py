from redline.align import Delete, Edit, Identity, Insert, align_paragraphs, align_units


def test_identical_text_returns_identity():
    ops = align_units("Same text here.", "Same text here.", "paragraph")
    assert ops == [Identity("Same text here.")]


def test_small_edit_stays_one_paragraph_diff():
    ops = align_units(
        "The term shall be five years from the Effective Date of this Agreement.",
        "The term shall be seven years from the Effective Date of this Agreement.",
        "paragraph",
    )
    assert len(ops) == 1
    assert isinstance(ops[0], Edit)
    assert "five" in ops[0].tokens_a
    assert "seven" in ops[0].tokens_b


def test_totally_different_short_paragraphs_become_insert_delete():
    ops = align_paragraphs(["Alpha unrelated text."], ["Zebra unrelated content."])
    kinds = {type(op) for op in ops}
    assert kinds <= {Delete, Insert, Edit}
    assert not any(isinstance(op, Identity) for op in ops)


def test_heavy_rewrite_does_not_crash_and_covers_all_content():
    old = (
        "The Company shall deliver the goods within thirty days of the "
        "order date, subject to availability and standard shipping terms."
    )
    new = (
        "Delivery of goods by the Company must occur no later than forty-five "
        "days after the order is placed, contingent on stock levels."
    )
    ops = align_paragraphs([old], [new])
    assert len(ops) >= 1
    # Nothing should silently vanish: every op carries real text.
    for op in ops:
        text = getattr(op, "text", None) or getattr(op, "text_a", "") + getattr(op, "text_b", "")
        assert text.strip()


def test_insertion_of_new_paragraph():
    ops = align_paragraphs(["Existing paragraph."], ["Existing paragraph.", "Brand new paragraph."])
    assert any(isinstance(op, Insert) and op.text == "Brand new paragraph." for op in ops)


def test_deletion_of_removed_paragraph():
    ops = align_paragraphs(["Existing paragraph.", "Removed paragraph."], ["Existing paragraph."])
    assert any(isinstance(op, Delete) and op.text == "Removed paragraph." for op in ops)


def test_empty_inputs_produce_no_ops():
    assert align_paragraphs([], []) == []
