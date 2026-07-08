"""Render Phase 0 blocks and Phase 1 ops as a standalone HTML redline.

<ins>/<del> mark word-level changes, matching the visual convention
described at the start of this project's design conversation. No
JavaScript, no external assets -- a single self-contained file.
"""

import html
from difflib import SequenceMatcher

from .align import Delete, Edit, Identity, Insert
from .blocks import Block
from .text import split_words

_CSS = """
body { font-family: Georgia, serif; max-width: 800px; margin: 2em auto; line-height: 1.5; }
ins { color: #0a7d2c; text-decoration: underline; background: #e6ffe9; }
del { color: #b3001b; text-decoration: line-through; background: #ffe6e6; }
p.identity { color: #333; }
"""


def render_html(items: list) -> str:
    """Render a list of Block/Identity/Edit/Insert/Delete items to HTML."""
    body = "\n".join(_render_item(item) for item in items)
    return (
        "<!DOCTYPE html>\n<html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style></head><body>\n{body}\n</body></html>"
    )


def _render_item(item) -> str:
    if isinstance(item, Block):
        return _render_block(item)
    if isinstance(item, Identity):
        return _paragraphs(item.text, "identity")
    if isinstance(item, Insert):
        return f"<p><ins>{html.escape(item.text)}</ins></p>"
    if isinstance(item, Delete):
        return f"<p><del>{html.escape(item.text)}</del></p>"
    if isinstance(item, Edit):
        return f"<p>{_render_edit(item)}</p>"
    raise TypeError(f"unknown redline item: {type(item)!r}")


def _render_block(block: Block) -> str:
    """"exact"/"whitespace" blocks are true no-op matches -- render as
    unchanged. "case" blocks matched cheaply in Phase 0 but must still
    show a visible diff (see blocks.py); do that with one direct difflib
    call rather than routing back through Phase 1's recursive matcher."""
    if block.transform in ("exact", "whitespace"):
        return _paragraphs(block.text_a, "identity")
    tokens_a, tokens_b = split_words(block.text_a), split_words(block.text_b)
    opcodes = tuple(SequenceMatcher(None, tokens_a, tokens_b, autojunk=False).get_opcodes())
    edit = Edit(block.text_a, block.text_b, tuple(tokens_a), tuple(tokens_b), opcodes)
    return f"<p>{_render_edit(edit)}</p>"


def _paragraphs(text: str, css_class: str) -> str:
    """A Block/Identity may span several original paragraphs (joined with
    blank lines when Phase 0 merged adjacent matches) -- render each as
    its own <p> rather than one blob with embedded blank lines."""
    parts = [p for p in text.split("\n\n") if p.strip()]
    return "\n".join(f"<p class='{css_class}'>{html.escape(p)}</p>" for p in parts)


def _render_edit(edit: Edit) -> str:
    parts = []
    for tag, i1, i2, j1, j2 in edit.opcodes:
        a_span = " ".join(edit.tokens_a[i1:i2])
        b_span = " ".join(edit.tokens_b[j1:j2])
        if tag == "equal":
            parts.append(html.escape(a_span))
        elif tag == "delete":
            parts.append(f"<del>{html.escape(a_span)}</del>")
        elif tag == "insert":
            parts.append(f"<ins>{html.escape(b_span)}</ins>")
        elif tag == "replace":
            parts.append(f"<del>{html.escape(a_span)}</del> <ins>{html.escape(b_span)}</ins>")
    return " ".join(parts)
