import pytest

from redline.cli import main


def _make_docx(path, paragraphs):
    docx = pytest.importorskip("docx", reason="python-docx not installed")
    doc = docx.Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(str(path))


def _make_odt(path, paragraphs):
    pytest.importorskip("odf", reason="odfpy not installed")
    from odf.opendocument import OpenDocumentText
    from odf.text import P

    doc = OpenDocumentText()
    for text in paragraphs:
        doc.text.addElement(P(text=text))
    doc.save(str(path))


def test_text_files_compared_and_written_to_stdout(tmp_path, capsys):
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text("The fee is $100 per month.")
    new.write_text("The fee is $150 per month.")

    code = main([str(old), str(new)])

    assert code == 0
    out = capsys.readouterr().out
    # Character-level word diffing (see render._render_token_pair) narrows
    # this to the differing digit rather than the whole token.
    assert "$1<ins>5</ins>0<del>0</del>" in out


def test_output_flag_writes_to_file(tmp_path):
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    out_path = tmp_path / "redline.html"
    old.write_text("Unchanged paragraph.")
    new.write_text("Unchanged paragraph.")

    code = main([str(old), str(new), "-o", str(out_path)])

    assert code == 0
    assert "<html>" in out_path.read_text()


def test_auto_detects_docx_from_extension(tmp_path):
    old = tmp_path / "old.docx"
    new = tmp_path / "new.docx"
    _make_docx(old, ["The fee is $100 per month."])
    _make_docx(new, ["The fee is $150 per month."])
    out_path = tmp_path / "out.html"

    code = main([str(old), str(new), "-o", str(out_path)])

    assert code == 0
    html = out_path.read_text()
    # Character-level word diffing (see render._render_token_pair) narrows
    # this to the differing digit rather than the whole token.
    assert "$1<ins>5</ins>0<del>0</del>" in html


def test_auto_detects_odt_from_extension(tmp_path):
    old = tmp_path / "old.odt"
    new = tmp_path / "new.odt"
    _make_odt(old, ["The fee is $100 per month."])
    _make_odt(new, ["The fee is $150 per month."])
    out_path = tmp_path / "out.html"

    code = main([str(old), str(new), "-o", str(out_path)])

    assert code == 0
    html = out_path.read_text()
    # Character-level word diffing (see render._render_token_pair) narrows
    # this to the differing digit rather than the whole token.
    assert "$1<ins>5</ins>0<del>0</del>" in html


def test_explicit_format_flag_overrides_extension(tmp_path):
    # Extension-less files: auto-detect would fall back to "text" and
    # misread these as plain text, so --format docx is required here.
    old = tmp_path / "old_contract"
    new = tmp_path / "new_contract"
    _make_docx(old, ["The fee is $100 per month."])
    _make_docx(new, ["The fee is $150 per month."])
    out_path = tmp_path / "out.html"

    code = main([str(old), str(new), "--format", "docx", "-o", str(out_path)])

    assert code == 0
    assert "$1<ins>5</ins>0<del>0</del>" in out_path.read_text()


def test_missing_file_reports_clean_error(tmp_path, capsys):
    old = tmp_path / "missing.txt"
    new = tmp_path / "new.txt"
    new.write_text("Some text.")

    code = main([str(old), str(new)])

    assert code == 1
    err = capsys.readouterr().err
    assert "no such file" in err
    assert str(old) in err


def test_version_flag_exits_zero_and_prints_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])

    assert exc_info.value.code == 0
    assert "redline" in capsys.readouterr().out


def test_suppress_moves_flag_disables_move_labeling(tmp_path):
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text(
        "Charlie paragraph moved to the end.\n\n"
        "Alpha paragraph unchanged.\n\n"
        "Bravo paragraph will be reworded."
    )
    new.write_text(
        "Alpha paragraph unchanged.\n\n"
        "Bravo paragraph has been reworded.\n\n"
        "Charlie paragraph moved to the end."
    )

    default_out = tmp_path / "default.html"
    suppressed_out = tmp_path / "suppressed.html"

    assert main([str(old), str(new), "-o", str(default_out)]) == 0
    assert main([str(old), str(new), "-o", str(suppressed_out), "--suppress-moves"]) == 0

    assert "class='moved'" in default_out.read_text()
    assert "class='moved'" not in suppressed_out.read_text()
    assert "<del>Charlie paragraph moved to the end.</del>" in suppressed_out.read_text()


def test_unrecognized_extension_falls_back_to_text(tmp_path):
    old = tmp_path / "old.md"
    new = tmp_path / "new.md"
    old.write_text("Unchanged paragraph.")
    new.write_text("Unchanged paragraph.")

    code = main([str(old), str(new)])

    assert code == 0
