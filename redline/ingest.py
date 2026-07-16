"""Paragraph extraction from plain text, .docx, .odt, and .pdf.

Only text is compared -- formatting (bold, italic, color, tables) is
explicitly out of scope for v1, per the project's "lightweight" goal.
Paragraph style names (e.g. "Heading 1") are extracted and available on
Paragraph.style. As of 2026-07-12, ``compare_pdf`` threads style through
to rendering for PDF-sourced headings (see ``from_pdf`` and
``pipeline.compare_pdf``); ``compare_text``/``compare_docx``/
``compare_odt`` still discard it (pipeline.py's ``_compare_paragraphs`` for
those paths only sees ``.text``), so headings from those formats still
render as plain paragraphs -- extending them the same way is a natural,
not-yet-done follow-up (see docs/API.md "Known limitations"). Tables are
not yet handled either.
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
        from_text("First.\n\nSecond.")
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


def from_pdf(path) -> list[Paragraph]:
    """Extract paragraphs from a PDF, via the shared ``readers`` package.

    Reworked 2026-07-12 (see readers/JOURNAL_2026-07-12.md "Option A") to
    use ``readers.split_into_sections`` instead of ``recover_paragraphs``
    directly: ordinary (non-heading) paragraph boundaries have no reliable
    signal in flat PDF text, and two revisions of the same document merge
    that ambiguous text differently, which made the diff engine compare
    mismatched blobs and render near-identical paragraphs as a full
    delete+insert. Collapsing everything between headings into one section
    body sidesteps that -- headings become their own Paragraph (with a
    text-derived heading level; pypdf gives no font-size signal, see
    readers/segment.py's ``_heading_level``), and the (usually large) body
    text between them is one Paragraph left for redline's own sentence-
    level recursive alignment to diff, rather than trying to further split
    it here.

    Raises:
        ImportError: if the readers package, or its pdf extra (pypdf),
            isn't installed.
        ValueError: if the PDF can't be read for any other reason (not
            found, corrupt, empty, permission denied) -- see
            readers.ReadStatus for the full set of non-success outcomes.

    Example:
        from_pdf("report.pdf")
        # -> [Paragraph("1 Introduction", "Heading 1"), Paragraph("Body text...")]
    """
    try:
        from readers import ReadStatus, read_file, split_into_sections
    except ImportError as exc:
        raise ImportError(
            "Reading .pdf files requires the 'readers' package with its "
            "pdf extra: pip install -e path/to/readers[pdf]"
        ) from exc

    result = read_file(str(path))
    if result.status is ReadStatus.UNSUPPORTED_FORMAT:
        raise ImportError(result.error)
    if not result.ok:
        raise ValueError(f"Could not read {path}: {result.error}")

    paragraphs: list[Paragraph] = []
    for heading, level, body in split_into_sections(result.content):
        if heading:
            paragraphs.append(Paragraph(heading, f"Heading {level}"))
        if body:
            paragraphs.append(Paragraph(body))
    return paragraphs


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
