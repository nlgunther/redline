"""Paragraph extraction from plain text and .docx.

Only text is compared -- formatting (bold, italic, color, tables) is
explicitly out of scope for v1, per the project's "lightweight" goal.
Paragraph style names (e.g. "Heading 1") are extracted and available on
Paragraph.style, but are NOT yet threaded through comparison or
rendering -- pipeline.py currently discards them, so headings render as
plain paragraphs today. Wiring style through Block/Insert/Delete/Edit so
the HTML output reproduces heading levels is a documented next step, not
done in this pass -- see docs/API.md "Known limitations". Tables are not
yet handled either.
"""

from dataclasses import dataclass

from .text import split_paragraphs


@dataclass(frozen=True)
class Paragraph:
    text: str
    style: str = "Normal"  # e.g. "Heading 1" -- render hint only, not compared


def from_text(raw: str) -> list[Paragraph]:
    """Split plain text into paragraphs on blank lines.

    Example:
        from_text("First.\\n\\nSecond.")
        # -> [Paragraph("First."), Paragraph("Second.")]
    """
    return [Paragraph(p) for p in split_paragraphs(raw)]


def from_odt(path) -> list[Paragraph]:
    """Extract paragraphs from an .odt file. Heading levels become a
    style label ("Heading N") to match from_docx's naming convention;
    ordinary paragraphs carry whatever style name ODF recorded, or
    "Normal" if none. Tables are skipped, same scope decision as
    from_docx. Requires odfpy.

    Raises:
        ImportError: if odfpy isn't installed.
    """
    try:
        from odf.opendocument import load
        from odf.teletype import extractText
    except ImportError as exc:
        raise ImportError(
            "Reading .odt files requires the 'odfpy' package: pip install odfpy"
        ) from exc

    document = load(str(path))
    return [p for p in (_odt_paragraph(el, extractText) for el in document.text.childNodes) if p]


def _odt_paragraph(el, extract_text) -> Paragraph | None:
    tag = el.qname[1] if getattr(el, "qname", None) else None
    if tag not in ("p", "h"):
        return None  # tables and other element types are out of scope
    text = extract_text(el).strip()
    if not text:
        return None
    if tag == "h":
        level = el.getAttribute("outlinelevel") or "1"
        return Paragraph(text, f"Heading {level}")
    return Paragraph(text, el.getAttribute("stylename") or "Normal")


def from_docx(path) -> list[Paragraph]:
    """Extract paragraphs from a .docx file, preserving style names.

    Raises:
        ImportError: if python-docx isn't installed.
    """
    try:
        import docx
    except ImportError as exc:
        raise ImportError(
            "Reading .docx files requires the 'python-docx' package: "
            "pip install python-docx"
        ) from exc

    document = docx.Document(str(path))
    return [
        Paragraph(p.text.strip(), p.style.name if p.style else "Normal")
        for p in document.paragraphs
        if p.text.strip()
    ]
