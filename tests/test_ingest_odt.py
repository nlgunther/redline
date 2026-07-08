import pytest

odf = pytest.importorskip("odf", reason="odfpy not installed")

from odf.opendocument import OpenDocumentText
from odf.text import H, P

from redline.ingest import from_odt
from redline.pipeline import compare_odt


def _make_odt(path, heading, paragraphs):
    doc = OpenDocumentText()
    if heading:
        doc.text.addElement(H(outlinelevel=1, text=heading))
    for text in paragraphs:
        doc.text.addElement(P(text=text))
    doc.save(str(path))


def test_from_odt_extracts_paragraphs_and_heading(tmp_path):
    path = tmp_path / "sample.odt"
    _make_odt(path, "Sample Agreement", ["First paragraph.", "Second paragraph."])

    paras = from_odt(path)

    assert [p.text for p in paras] == ["Sample Agreement", "First paragraph.", "Second paragraph."]
    assert paras[0].style == "Heading 1"
    assert paras[1].style == "Normal"


def test_from_odt_skips_empty_paragraphs(tmp_path):
    path = tmp_path / "sample.odt"
    _make_odt(path, None, ["Real text.", "", "   "])

    paras = from_odt(path)

    assert [p.text for p in paras] == ["Real text."]


def test_compare_odt_end_to_end(tmp_path):
    old_path = tmp_path / "old.odt"
    new_path = tmp_path / "new.odt"
    _make_odt(old_path, "Title", ["Unchanged paragraph.", "The fee is $100 per month."])
    _make_odt(new_path, "Title", ["Unchanged paragraph.", "The fee is $150 per month."])

    html = compare_odt(old_path, new_path)

    assert "<del>$100</del>" in html
    assert "<ins>$150</ins>" in html
    assert html.count("class='identity'") == 2  # heading + unchanged paragraph
