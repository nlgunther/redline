"""Top-level orchestration: Phase 0 (block removal) then Phase 1
(recursive matching) on the residual holes, in document order.

Key simplification confirmed during design: once Phase 0's blocks are
ordered, they form a spine anchoring both documents. The hole in A
between block i and block i+1 corresponds, by construction, to the hole
in B between the same two blocks -- no separate whole-document candidate
search is needed for this pairing. That's why Phase 0's ordering
constraint (the LIS resolution in blocks.py) matters for Phase 1 too, not
just for Phase 0 itself.
"""

from .align import align_paragraphs
from .blocks import Block, find_blocks
from .ingest import from_docx, from_odt, from_pdf, from_text
from .moves import detect_moves as _detect_moves
from .render import render_html


def compare_text(old_text: str, new_text: str, detect_moves: bool = True) -> str:
    """Compare two plain-text documents and return a standalone HTML redline."""
    paras_a = [p.text for p in from_text(old_text)]
    paras_b = [p.text for p in from_text(new_text)]
    return render_html(_compare_paragraphs(paras_a, paras_b, detect_moves))


def compare_docx(old_path, new_path, detect_moves: bool = True) -> str:
    """Compare two .docx files and return a standalone HTML redline."""
    paras_a = [p.text for p in from_docx(old_path)]
    paras_b = [p.text for p in from_docx(new_path)]
    return render_html(_compare_paragraphs(paras_a, paras_b, detect_moves))


def compare_odt(old_path, new_path, detect_moves: bool = True) -> str:
    """Compare two .odt files and return a standalone HTML redline."""
    paras_a = [p.text for p in from_odt(old_path)]
    paras_b = [p.text for p in from_odt(new_path)]
    return render_html(_compare_paragraphs(paras_a, paras_b, detect_moves))


def compare_pdf(old_path, new_path, detect_moves: bool = True) -> str:
    """Compare two .pdf files and return a standalone HTML redline.

    Unlike compare_text/compare_docx/compare_odt, this threads heading
    style through to rendering (2026-07-12, see
    readers/JOURNAL_2026-07-12.md "Option A"): from_pdf's headings are
    detected via readers.split_into_sections' text heuristic (no font-size
    signal is available from pypdf). style_by_text maps each heading
    Paragraph's exact text to its style, looked up by render_html per
    rendered item -- deliberately not touching Block/Identity/Edit/Insert/
    Delete's dataclasses (blocks.py/align.py) to carry style themselves,
    since every one of those already carries the paragraph text verbatim,
    so a text-keyed lookup gets the same result without widening those
    types' shape. Only the PDF path is wired this way; extending
    compare_docx/compare_odt the same way (they already extract style,
    see ingest.py's module docstring) is a natural follow-up, not done in
    this pass.
    """
    old_paras = from_pdf(old_path)
    new_paras = from_pdf(new_path)
    style_by_text = {
        p.text: p.style for p in old_paras + new_paras if p.style != "Normal"
    }
    paras_a = [p.text for p in old_paras]
    paras_b = [p.text for p in new_paras]
    return render_html(_compare_paragraphs(paras_a, paras_b, detect_moves), style_by_text)


def _compare_paragraphs(paras_a: list[str], paras_b: list[str], detect_moves: bool = True) -> list:
    blocks, _, _ = find_blocks(paras_a, paras_b)
    items = _stitch(paras_a, paras_b, blocks)
    return _detect_moves(items) if detect_moves else items


def _stitch(paras_a: list[str], paras_b: list[str], blocks: list[Block]) -> list:
    """Walk the anchor spine in order: fill each hole via Phase 1, then
    emit the anchoring Block itself."""
    items = []
    last_a, last_b = 0, 0
    for block in blocks:
        items.extend(_fill_hole(paras_a, paras_b, last_a, block.index_a.start, last_b, block.index_b.start))
        items.append(block)
        last_a, last_b = block.index_a.stop, block.index_b.stop
    items.extend(_fill_hole(paras_a, paras_b, last_a, len(paras_a), last_b, len(paras_b)))
    return items


def _fill_hole(paras_a, paras_b, a_start, a_end, b_start, b_end) -> list:
    return align_paragraphs(paras_a[a_start:a_end], paras_b[b_start:b_end])
