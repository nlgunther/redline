from redline.align import Delete, Edit, Insert
from redline.blocks import Block
from redline.pipeline import compare_text


def _kinds(items):
    return [type(item).__name__ for item in items]


def test_light_edit_document_mostly_identity():
    old = "Paragraph one is unchanged.\n\nParagraph two has old wording here.\n\nParagraph three is unchanged."
    new = "Paragraph one is unchanged.\n\nParagraph two has new wording here.\n\nParagraph three is unchanged."
    from redline.pipeline import _compare_paragraphs
    from redline.text import split_paragraphs

    items = _compare_paragraphs(split_paragraphs(old), split_paragraphs(new))
    assert sum(isinstance(i, Block) for i in items) == 2  # two unchanged paragraphs
    assert any(isinstance(i, Edit) for i in items)


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
    assert "<del>Agreement</del>" in html
    assert "<ins>agreement</ins>" in html


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
