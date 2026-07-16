import sys

import pytest

readers = pytest.importorskip("readers", reason="readers package not installed")

reportlab_canvas = pytest.importorskip(
    "reportlab.pdfgen.canvas", reason="reportlab not installed"
)

from redline.ingest import from_pdf
from redline.pipeline import compare_pdf


def _make_pdf(path, pages):
    """pages: list[list[str]] -- one list of lines per page."""
    from reportlab.lib.pagesizes import letter

    c = reportlab_canvas.Canvas(str(path), pagesize=letter)
    for lines in pages:
        y = 720
        for line in lines:
            c.drawString(72, y, line)
            y -= 20
        c.showPage()
    c.save()


def test_from_pdf_extracts_paragraphs_across_pages(tmp_path):
    path = tmp_path / "sample.pdf"
    _make_pdf(path, [["Executive Summary"], ["First page body line."]])

    paras = from_pdf(path)

    assert [p.text for p in paras] == ["Executive Summary", "First page body line."]
    assert all(p.style == "Normal" for p in paras)


def test_compare_pdf_end_to_end(tmp_path):
    old_path = tmp_path / "old.pdf"
    new_path = tmp_path / "new.pdf"
    _make_pdf(old_path, [["The fee is $100 per month."]])
    _make_pdf(new_path, [["The fee is $150 per month."]])

    html = compare_pdf(old_path, new_path)

    assert "$1<ins>5</ins>0<del>0</del>" in html


def test_from_pdf_raises_import_error_when_readers_missing(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "readers", None)
    with pytest.raises(ImportError, match="readers"):
        from_pdf(tmp_path / "does-not-matter.pdf")


def test_from_pdf_raises_import_error_when_pypdf_missing(tmp_path, monkeypatch):
    def fake_read_file(path):
        return readers.ReadResult(
            filepath=str(path),
            status=readers.ReadStatus.UNSUPPORTED_FORMAT,
            error="pypdf not installed -- run: pip install 'readers[pdf]'",
        )

    monkeypatch.setattr(readers, "read_file", fake_read_file)
    with pytest.raises(ImportError, match="pypdf"):
        from_pdf(tmp_path / "sample.pdf")


def test_from_pdf_raises_value_error_for_other_failures(tmp_path, monkeypatch):
    def fake_read_file(path):
        return readers.ReadResult(
            filepath=str(path),
            status=readers.ReadStatus.CORRUPT_FILE,
            error="Corrupt PDF: bad xref table",
        )

    monkeypatch.setattr(readers, "read_file", fake_read_file)
    with pytest.raises(ValueError, match="Corrupt PDF"):
        from_pdf(tmp_path / "sample.pdf")
