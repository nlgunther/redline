"""Render Phase 0 blocks and Phase 1 ops as a standalone HTML redline.

<ins>/<del> mark word-level changes, matching the visual convention
described at the start of this project's design conversation. No
JavaScript, no external assets -- a single self-contained file.
"""

import html
import string
from difflib import SequenceMatcher

from .align import Delete, Edit, Identity, Insert
from .blocks import Block
from .text import split_words

_CSS = """
body { font-family: Georgia, serif; max-width: 800px; margin: 2em auto; line-height: 1.5; }
ins { color: #0a7d2c; text-decoration: underline; background: #e6ffe9; }
del { color: #b3001b; text-decoration: line-through; background: #ffe6e6; }
p.identity { color: #333; }
h1, h2, h3, h4, h5, h6 { font-family: Georgia, serif; }
"""

# Minimum difflib character-ratio for a replaced word pair to get a
# character-level diff instead of a whole-word swap (see _render_replace).
# split_words() glues trailing/leading punctuation to words, so a token
# like `technology".` vs `technology"` is a full "replace" at word
# granularity even though only the period changed -- below this threshold
# the words are unrelated enough that a whole-word del+ins reads better
# than a noisy character diff.
WORD_CHAR_THRESHOLD = 0.5


def render_html(items: list, style_by_text: dict | None = None) -> str:
    """Render a list of Block/Identity/Edit/Insert/Delete items to HTML.

    style_by_text (added 2026-07-12, see readers/JOURNAL_2026-07-12.md
    "Option A"): optional map of exact paragraph text -> style (e.g.
    "Heading 1"), used to render that paragraph as <h1>-<h6> instead of
    <p>. Currently only passed by pipeline.compare_pdf; every other
    compare_* still renders plain <p> for every paragraph (see ingest.py's
    module docstring for why).
    """
    body = "\n".join(_render_item(item, style_by_text) for item in items)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>\n{body}\n</body></html>"
    )


def _tag_for(text: str, style_by_text: dict | None) -> str:
    """"h1"-"h6" if `text` is an exact match for a heading-styled
    paragraph, else the default "p". Text-keyed rather than carried on
    Block/Identity/Edit/Insert/Delete themselves -- every one of those
    already carries the paragraph text verbatim, so this gets the same
    result without widening those dataclasses' shape (blocks.py/align.py)
    just for this one PDF-only feature."""
    style = (style_by_text or {}).get(text, "")
    if not style.startswith("Heading"):
        return "p"
    level = style.rsplit(" ", 1)[-1]
    return f"h{level}" if level.isdigit() else "h1"


def _render_item(item, style_by_text: dict | None = None) -> str:
    if isinstance(item, Block):
        return _render_block(item, style_by_text)
    if isinstance(item, Identity):
        return _paragraphs(item.text, "identity", style_by_text)
    if isinstance(item, Insert):
        tag = _tag_for(item.text, style_by_text)
        return f"<{tag}><ins>{html.escape(item.text)}</ins></{tag}>"
    if isinstance(item, Delete):
        tag = _tag_for(item.text, style_by_text)
        return f"<{tag}><del>{html.escape(item.text)}</del></{tag}>"
    if isinstance(item, Edit):
        tag = _tag_for(item.text_a, style_by_text)
        if tag == "p":
            tag = _tag_for(item.text_b, style_by_text)
        return f"<{tag}>{_render_edit(item)}</{tag}>"
    raise TypeError(f"unknown redline item: {type(item)!r}")


def _render_block(block: Block, style_by_text: dict | None = None) -> str:
    """"exact"/"whitespace" blocks are true no-op matches -- render as
    unchanged. "case" blocks matched cheaply in Phase 0 but must still
    show a visible diff (see blocks.py); do that with one direct difflib
    call rather than routing back through Phase 1's recursive matcher."""
    if block.transform in ("exact", "whitespace"):
        return _paragraphs(block.text_a, "identity", style_by_text)
    tokens_a, tokens_b = split_words(block.text_a), split_words(block.text_b)
    opcodes = tuple(SequenceMatcher(None, tokens_a, tokens_b, autojunk=False).get_opcodes())
    edit = Edit(block.text_a, block.text_b, tuple(tokens_a), tuple(tokens_b), opcodes)
    tag = _tag_for(block.text_a, style_by_text)
    if tag == "p":
        tag = _tag_for(block.text_b, style_by_text)
    return f"<{tag}>{_render_edit(edit)}</{tag}>"


def _paragraphs(text: str, css_class: str, style_by_text: dict | None = None) -> str:
    """A Block/Identity may span several original paragraphs (joined with
    blank lines when Phase 0 merged adjacent matches) -- render each as
    its own <p>/<hN> rather than one blob with embedded blank lines."""
    parts = [p for p in text.split("\n\n") if p.strip()]
    out = []
    for p in parts:
        tag = _tag_for(p, style_by_text)
        out.append(f"<{tag} class='{css_class}'>{html.escape(p)}</{tag}>")
    return "\n".join(out)


def _render_edit(edit: Edit) -> str:
    parts = []
    for tag, i1, i2, j1, j2 in edit.opcodes:
        if tag == "equal":
            parts.append(html.escape(" ".join(edit.tokens_a[i1:i2])))
        elif tag == "delete":
            parts.append(f"<del>{html.escape(' '.join(edit.tokens_a[i1:i2]))}</del>")
        elif tag == "insert":
            parts.append(f"<ins>{html.escape(' '.join(edit.tokens_b[j1:j2]))}</ins>")
        elif tag == "replace":
            parts.append(_render_replace(edit.tokens_a[i1:i2], edit.tokens_b[j1:j2]))
    return " ".join(parts)


def _render_replace(a_tokens: tuple, b_tokens: tuple) -> str:
    """Render a word-level "replace" span. Word-for-word replacements
    (same token count on both sides) are diffed one pair at a time via
    _render_token_pair, so a punctuation-only or single-letter change
    doesn't flag the whole word. A different token count (a phrase
    swapped for a different-length phrase) has no natural word-by-word
    pairing, but the joined spans still get one character-level diff
    attempt (same WORD_CHAR_THRESHOLD gate, OR'd with a word-level
    containment check -- see _shorter_side_is_contained) before falling
    back to a whole-span delete+insert.
    """
    if len(a_tokens) == len(b_tokens):
        return " ".join(_render_token_pair(a, b) for a, b in zip(a_tokens, b_tokens))
    a_span, b_span = " ".join(a_tokens), " ".join(b_tokens)
    sm = SequenceMatcher(None, a_span, b_span, autojunk=False)
    if sm.ratio() >= WORD_CHAR_THRESHOLD or _shorter_side_is_contained(a_tokens, b_tokens):
        return _char_diff_html(a_span, b_span, sm)
    return f"<del>{html.escape(a_span)}</del> <ins>{html.escape(b_span)}</ins>"


def _shorter_side_is_contained(a_tokens: tuple, b_tokens: tuple) -> bool:
    """True if every word in the shorter token list -- modulo leading/
    trailing punctuation -- also appears in the longer one.

    Regression fix: sm.ratio() on the joined spans is a character-level
    ratio, which (like plain Jaccard in similarity.py) penalizes size
    disparity even under perfect containment. A short replaced token like
    'incorrect.' followed by a much longer new phrase that still opens
    with 'incorrect' scores a low ratio purely because of the length
    difference, so it fell through to a whole-span swap and re-marked
    the shared word as changed. This check catches that case at word
    granularity instead of raw characters -- a raw character-level
    containment check was tried and rejected because it also fires on
    coincidental prefixes of unrelated words (e.g. 'cat' is a character
    prefix of 'category', but they're different words); comparing whole,
    punctuation-stripped words avoids that false positive.
    """
    shorter, longer = (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    strip = lambda w: w.strip(string.punctuation).lower()
    shorter_words = {strip(w) for w in shorter} - {""}
    longer_words = {strip(w) for w in longer} - {""}
    return bool(shorter_words) and shorter_words <= longer_words


def _render_token_pair(a: str, b: str) -> str:
    """Character-level diff for one replaced word pair. Only used when
    the pair clears WORD_CHAR_THRESHOLD -- otherwise a single-letter typo
    and a completely unrelated word would render identically (both as a
    full word swap), which is the noise this refinement exists to avoid.
    """
    if a == b:
        return html.escape(a)
    sm = SequenceMatcher(None, a, b, autojunk=False)
    if sm.ratio() < WORD_CHAR_THRESHOLD:
        return f"<del>{html.escape(a)}</del> <ins>{html.escape(b)}</ins>"
    return _char_diff_html(a, b, sm)


def _char_diff_html(a: str, b: str, sm: SequenceMatcher) -> str:
    """Render sm's opcodes (already computed for a vs b) as inline
    character-level <del>/<ins> markup. Shared by _render_token_pair
    (same-count word pairs) and _render_replace (different-count spans,
    joined and diffed as one string) -- both callers have already checked
    WORD_CHAR_THRESHOLD (or the containment fallback) before calling this.
    """
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        a_chunk, b_chunk = a[i1:i2], b[j1:j2]
        if tag == "equal":
            parts.append(html.escape(a_chunk))
        elif tag == "delete":
            parts.append(f"<del>{html.escape(a_chunk)}</del>")
        elif tag == "insert":
            parts.append(f"<ins>{html.escape(b_chunk)}</ins>")
        elif tag == "replace":
            parts.append(f"<del>{html.escape(a_chunk)}</del><ins>{html.escape(b_chunk)}</ins>")
    return "".join(parts)
