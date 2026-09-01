from redline.align import (
    Delete,
    Edit,
    Identity,
    Insert,
    ParagraphGroup,
    _align_sequence,
    align_paragraphs,
    align_units,
)


def _items(groups: list[ParagraphGroup]) -> list:
    """Flatten align_paragraphs' ParagraphGroup wrapper back to a plain
    list of Identity/Edit/Insert/Delete, for tests that only care about
    the ops themselves, not which rendered paragraph they landed in."""
    return [item for group in groups for item in group.items]


def test_identical_text_returns_identity():
    ops = align_units("Same text here.", "Same text here.", "sentence")
    assert ops == [Identity("Same text here.")]


def test_small_edit_stays_one_paragraph_diff():
    ops = align_units(
        "The term shall be five years from the Effective Date of this Agreement.",
        "The term shall be seven years from the Effective Date of this Agreement.",
        "sentence",
    )
    assert len(ops) == 1
    assert isinstance(ops[0], Edit)
    assert "five" in ops[0].tokens_a
    assert "seven" in ops[0].tokens_b


def test_totally_different_short_paragraphs_become_insert_delete():
    ops = _items(align_paragraphs(["Alpha unrelated text."], ["Zebra unrelated content."]))
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
    ops = _items(align_paragraphs([old], [new]))
    assert len(ops) >= 1
    # Nothing should silently vanish: every op carries real text.
    for op in ops:
        text = getattr(op, "text", None) or getattr(op, "text_a", "") + getattr(op, "text_b", "")
        assert text.strip()


def test_insertion_of_new_paragraph():
    ops = _items(align_paragraphs(["Existing paragraph."], ["Existing paragraph.", "Brand new paragraph."]))
    assert any(isinstance(op, Insert) and op.text == "Brand new paragraph." for op in ops)


def test_deletion_of_removed_paragraph():
    ops = _items(align_paragraphs(["Existing paragraph.", "Removed paragraph."], ["Existing paragraph."]))
    assert any(isinstance(op, Delete) and op.text == "Removed paragraph." for op in ops)


def test_empty_inputs_produce_no_ops():
    assert align_paragraphs([], []) == []


def test_1v1_pairs_unconditionally_even_when_totally_dissimilar():
    # Regression test: being the only candidate on each side is sufficient
    # justification to pair, regardless of PAIR_THRESHOLD (0.15). Before
    # this fix, a 1-vs-1 hole with no word overlap fell through to a
    # disconnected Delete+Insert instead of one Edit.
    pairs, unmatched_a, unmatched_b = _align_sequence(
        ["Completely unrelated sentence here."], ["Totally different content indeed."]
    )
    assert pairs == [(0, 0)]
    assert unmatched_a == []
    assert unmatched_b == []


def test_1v1_forced_pairing_produces_single_edit_end_to_end():
    ops = _items(align_paragraphs(
        ["Completely unrelated sentence here."], ["Totally different content indeed."]
    ))
    assert len(ops) == 1
    assert isinstance(ops[0], Edit)


def test_1vM_still_gated_by_pair_threshold():
    # With more than one candidate on a side, an unrelated pairing must
    # still be rejected by PAIR_THRESHOLD -- the unconditional-pairing
    # special case is 1-vs-1 only, not "small hole in general".
    pairs, unmatched_a, unmatched_b = _align_sequence(
        ["Alpha bravo charlie delta.", "Totally different content indeed."],
        ["Totally different content indeed, restated."],
    )
    assert (0, 0) not in pairs


def test_word_level_replace_stays_one_edit_not_word_by_word_fragments():
    # Regression test (see docs/JOURNAL_2026-07-22.md): before this fix,
    # a dissimilar-enough sentence recursed into word-level candidate
    # pairing scored by similarity_score, which treats each argument as
    # a word set -- two single words only ever score 0 or 1, so every
    # non-identical word became its own disconnected Delete/Insert
    # instead of one coherent replace span.
    old = "The Company shall promptly furnish acceptable replacement merchandise to the aggrieved customer."
    new = "The Vendor must immediately supply suitable substitute goods to the affected client."
    ops = align_units(old, new, "sentence")
    assert len(ops) == 1
    assert isinstance(ops[0], Edit)


# --- paragraph-boundary-agnostic sentence matching (reworked 2026-07-21) ---


def test_paragraph_split_does_not_break_identical_sentence_matching():
    # Regression test for the real bug found in main-15a.tex vs main-14a.tex
    # (see docs/JOURNAL_2026-07-21.md): the old paragraph had two sentences
    # on one line (no blank line between them); the new paragraph split
    # them apart with a blank line and reworded only the first one. Under
    # the old paragraph-pairing design, the single old paragraph could only
    # be paired with ONE of the two new paragraphs, so the other rendered
    # as a disconnected insert even though its sentence is unchanged.
    old_para = "Shared opening sentence. Shared closing sentence."
    new_para_a = "Shared opening sentence, reworded."
    new_para_b = "Shared closing sentence."

    groups = align_paragraphs([old_para], [new_para_a, new_para_b])
    ops = _items(groups)

    assert any(isinstance(op, Identity) and op.text == "Shared closing sentence." for op in ops)
    assert not any(
        isinstance(op, (Insert, Delete)) and "Shared closing sentence" in op.text for op in ops
    )


def test_paragraph_split_still_isolates_the_actual_change():
    # Same case as above, but checking the *only* other op is the real
    # edit -- nothing else gets swept up as a spurious insert/delete.
    old_para = "Shared opening sentence. Shared closing sentence."
    new_para_a = "Shared opening sentence, reworded."
    new_para_b = "Shared closing sentence."

    ops = _items(align_paragraphs([old_para], [new_para_a, new_para_b]))
    non_identity = [op for op in ops if not isinstance(op, Identity)]
    assert len(non_identity) == 1
    assert isinstance(non_identity[0], Edit)
    assert non_identity[0].text_a == "Shared opening sentence."
    assert non_identity[0].text_b == "Shared opening sentence, reworded."


def test_paragraph_merge_is_the_symmetric_case():
    # The reverse of a split: two old paragraphs merge into one new
    # paragraph. The shared sentence should still be recognized as
    # unchanged regardless of which paragraph it's nominally in.
    old_para_a = "First sentence stays the same."
    old_para_b = "Second sentence changes here."
    new_para = "First sentence stays the same. Second sentence is different now."

    ops = _items(align_paragraphs([old_para_a, old_para_b], [new_para]))
    assert any(isinstance(op, Identity) and op.text == "First sentence stays the same." for op in ops)


def test_reordered_identical_sentences_stay_identity():
    # Regression test: _align_sequence alone is order-preserving and can't
    # represent a crossing correspondence, so two sentences that are
    # simply swapped relative to each other used to render as two Edits
    # even though neither one's wording changed (see the "later same day"
    # entry in docs/JOURNAL_2026-07-21.md). The exact-match pre-pass finds
    # both by content, independent of position.
    old_para = "Alpha content stays the same. Beta content stays the same too."
    new_para = "Beta content stays the same too. Alpha content stays the same."

    ops = _items(align_paragraphs([old_para], [new_para]))
    assert all(isinstance(op, Identity) for op in ops)
    assert {op.text for op in ops} == {
        "Alpha content stays the same.",
        "Beta content stays the same too.",
    }


def test_reordered_sentences_alongside_a_real_edit_and_insertion():
    # A swap plus unrelated changes in the same hole: the swapped pair
    # must still both come out as Identity, and the genuine edit/insert
    # must not be disturbed by the merge between anchor and residual ops.
    old_para = "Alpha stays the same. Beta stays the same too. Gamma will be reworded."
    new_para = (
        "Beta stays the same too. Alpha stays the same. "
        "Gamma has been reworded. Delta is brand new."
    )

    ops = _items(align_paragraphs([old_para], [new_para]))
    kinds = [type(op).__name__ for op in ops]
    assert kinds.count("Identity") == 2
    assert kinds.count("Edit") == 1
    assert kinds.count("Insert") == 1
    identity_texts = {op.text for op in ops if isinstance(op, Identity)}
    assert identity_texts == {"Alpha stays the same.", "Beta stays the same too."}


def test_wholly_deleted_paragraph_groups_as_its_own_block():
    # A paragraph with no counterpart at all on the new side should still
    # render as one cohesive deleted block, not glued onto a neighbor.
    groups = align_paragraphs(
        ["Kept opening paragraph.", "Entirely removed paragraph gone now.", "Kept closing paragraph."],
        ["Kept opening paragraph.", "Kept closing paragraph."],
    )
    kinds_per_group = [[type(item).__name__ for item in g.items] for g in groups]
    # The deleted paragraph's sentence(s) should form their own group,
    # distinct from the kept opening/closing paragraphs' groups.
    delete_groups = [g for g in groups if any(isinstance(i, Delete) for i in g.items)]
    assert len(delete_groups) == 1
    assert all(isinstance(i, Delete) for i in delete_groups[0].items)
