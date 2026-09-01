from redline.align import Delete, Edit, Insert, ParagraphGroup
from redline.blocks import Block
from redline.pipeline import _compare_paragraphs, compare_text
from redline.render import render_html


def _kinds(items):
    return [type(item).__name__ for item in items]


def test_light_edit_document_mostly_identity():
    old = "Paragraph one is unchanged.\n\nParagraph two has old wording here.\n\nParagraph three is unchanged."
    new = "Paragraph one is unchanged.\n\nParagraph two has new wording here.\n\nParagraph three is unchanged."
    from redline.text import split_paragraphs

    items = _compare_paragraphs(split_paragraphs(old), split_paragraphs(new))
    assert sum(isinstance(i, Block) for i in items) == 2  # two unchanged paragraphs
    groups = [i for i in items if isinstance(i, ParagraphGroup)]
    assert any(isinstance(op, Edit) for g in groups for op in g.items)


def test_heavily_revised_document_no_crash():
    old = "\n\n".join(f"Old paragraph number {i} with some filler content." for i in range(20))
    new = "\n\n".join(f"Completely different paragraph {i} about other things entirely." for i in range(20))
    html = compare_text(old, new)
    assert "<html>" in html
    assert "<del>" in html or "<ins>" in html


def test_moved_section_renders_without_error():
    old = "Alpha section text.\n\nBravo section text.\n\nCharlie section text."
    new = "Bravo section text.\n\nAlpha section text.\n\nCharlie section text."
    html = compare_text(old, new)
    assert "Alpha section text." in html
    assert "Bravo section text." in html
    assert "Charlie section text." in html


def test_case_only_change_visible_in_final_html():
    old = "The Agreement is binding on both parties."
    new = "The agreement is binding on both parties."
    html = compare_text(old, new)
    # Character-level word diffing (see render._render_token_pair) narrows
    # this to just the differing letter rather than the whole word.
    assert "<del>A</del><ins>a</ins>greement" in html


def test_pure_insertion_document():
    old = "Only paragraph."
    new = "Only paragraph.\n\nA brand new clause was added here."
    html = compare_text(old, new)
    assert "<ins>A brand new clause was added here.</ins>" in html


def test_identical_documents_produce_only_identity():
    text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    html = compare_text(text, text)
    assert "<del>" not in html
    assert "<ins>" not in html


def test_paragraph_split_end_to_end_via_compare_text():
    # End-to-end reproduction of the real main-15a.tex vs main-14a.tex bug
    # (see docs/JOURNAL_2026-07-21.md): old has one paragraph holding two
    # sentences with no blank line between them; new splits them into two
    # paragraphs and rewords only the first. The unchanged second sentence
    # must not render as a disconnected insert+delete.
    old = "Shared opening sentence. Shared closing sentence."
    new = "Shared opening sentence, reworded.\n\nShared closing sentence."
    html = compare_text(old, new)
    assert "<del>Shared closing sentence.</del>" not in html
    assert "<ins>Shared closing sentence.</ins>" not in html
    assert "Shared closing sentence." in html
    assert "<ins>, reworded</ins>" in html or "<ins>reworded</ins>" in html or "reworded" in html


def test_sentence_reorder_within_a_hole_renders_as_identity_end_to_end():
    # End-to-end reproduction of the swapped-sentence case (see the "later
    # same day" entry in docs/JOURNAL_2026-07-21.md): two sentences swap
    # places, forced into the same Phase 1 hole by an unrelated edit
    # elsewhere in the paragraph. Neither swapped sentence actually
    # changed wording, so neither should render as <del>/<ins>.
    old = "Alpha stays the same. Beta stays the same too. Gamma will be reworded."
    new = "Beta stays the same too. Alpha stays the same. Gamma has been reworded."
    html = compare_text(old, new)
    assert "<del>Alpha" not in html
    assert "<ins>Alpha" not in html
    assert "<del>Beta" not in html
    assert "<ins>Beta" not in html
    assert "Alpha stays the same." in html
    assert "Beta stays the same too." in html


def test_cross_hole_move_renders_as_labeled_move_not_delete_plus_insert():
    # End-to-end reproduction of the Charlie/Alpha/Bravo example (see
    # docs/JOURNAL_2026-07-22.md): "Alpha" is the only paragraph both
    # documents agree stays in place, so it's the sole Phase 0 anchor --
    # everything before it and everything after it are separate Phase 1
    # holes. Charlie's old position (before Alpha) and new position
    # (after Bravo) are in different holes, so only the whole-document
    # moves.detect_moves pass (run by _compare_paragraphs after _stitch)
    # can recognize it as relocated rather than deleted-then-reinserted.
    old = "\n\n".join([
        "Charlie paragraph moved to the end.",
        "Alpha paragraph unchanged.",
        "Bravo paragraph will be reworded.",
    ])
    new = "\n\n".join([
        "Alpha paragraph unchanged.",
        "Bravo paragraph has been reworded.",
        "Charlie paragraph moved to the end.",
    ])

    html = compare_text(old, new)

    assert "<del>Charlie paragraph moved to the end.</del>" not in html
    assert "<ins>Charlie paragraph moved to the end.</ins>" not in html
    assert "{moved below}" in html
    assert "{moved from above} Charlie paragraph moved to the end." in html


def test_suppress_moves_flag_falls_back_to_plain_delete_and_insert():
    old = "\n\n".join([
        "Charlie paragraph moved to the end.",
        "Alpha paragraph unchanged.",
        "Bravo paragraph will be reworded.",
    ])
    new = "\n\n".join([
        "Alpha paragraph unchanged.",
        "Bravo paragraph has been reworded.",
        "Charlie paragraph moved to the end.",
    ])

    html = compare_text(old, new, detect_moves=False)

    assert "class='moved'" not in html
    assert "<del>Charlie paragraph moved to the end.</del>" in html
    assert "<ins>Charlie paragraph moved to the end.</ins>" in html


def test_style_by_text_renders_heading_paragraph_as_heading_tag():
    # Simulates what compare_pdf does: build style_by_text from headings
    # detected on either side, thread it through render_html. Doesn't
    # require an actual PDF fixture -- _compare_paragraphs/render_html are
    # the same functions compare_pdf calls internally.
    old = ["1 Intro", "Body text is unchanged here."]
    new = ["1 Intro", "Body text is unchanged here."]
    style_by_text = {"1 Intro": "Heading 1"}
    html = render_html(_compare_paragraphs(old, new), style_by_text)
    assert "<h1 class='identity'>1 Intro</h1>" in html
    assert "<p class='identity'>Body text is unchanged here.</p>" in html
