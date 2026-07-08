# redline — Test Suite Reference

Quick reference for adding new tests. Update this file whenever a new test
file is created or a significant pattern changes.

---

## Layout

```
tests/
├── __init__.py       # empty, makes tests a package
├── test_text.py       # normalization + splitting (text.py)
├── test_blocks.py     # Phase 0 exact/near-exact block matching (blocks.py)
├── test_align.py      # Phase 1 recursive matcher (align.py)
├── test_pipeline.py   # end-to-end compare_text() and internals (pipeline.py)
├── test_ingest_odt.py # .odt extraction and compare_odt() end-to-end
└── test_cli.py         # argument parsing, format auto-detection, exit codes (cli.py)
```

**Framework:** pytest
**Config:** `pyproject.toml` → `[tool.pytest.ini_options]`
`testpaths = ["tests"]`, `pythonpath = ["."]`
No `conftest.py` — the suite is small enough that no shared fixtures are
needed yet.

---

## Fixture Patterns

No `@pytest.fixture` is used anywhere in this suite. Every test builds its
own small input inline — appropriate given inputs are just short strings
or lists of strings, not database connections or tempdirs. If a future
test needs a real `.docx` file on disk, build it in the test itself with
`python-docx` (see the ad hoc example used in manual testing during
development) rather than adding a fixture for a single test.

```python
import docx

def test_docx_ingestion(tmp_path):
    doc = docx.Document()
    doc.add_paragraph("Some text.")
    path = tmp_path / "sample.docx"
    doc.save(str(path))
    # ... assert against redline.ingest.from_docx(path)
```

Use pytest's built-in `tmp_path` fixture for any test that needs to write
a real file — don't invent a custom tempdir fixture.

For tests that depend on an optional dependency (e.g. `odfpy` for
`.odt` support), use `pytest.importorskip` at module level rather than a
fixture, so the whole file cleanly skips instead of erroring if the
dependency isn't installed:

```python
odf = pytest.importorskip("odf", reason="odfpy not installed")
```

`test_cli.py` needs this per-test rather than at module level, since only
some of its tests touch `.docx`/`.odt` — it calls `pytest.importorskip`
inside the small `_make_docx`/`_make_odt` helpers instead of at the top of
the file, so plain-text CLI tests still run with neither dependency
installed.

### Testing a CLI entry point without subprocess

`cli.main(argv)` takes an explicit argument list and returns an exit code
rather than calling `sys.exit()` itself (except for `argparse`'s own
`--version`/`--help`/error paths, which raise `SystemExit` directly) — this
makes it callable in-process like any other function, so there's no need
for `subprocess` + parsing stdout/stderr text streams:

```python
import pytest
from redline.cli import main

def test_something(tmp_path, capsys):
    code = main([str(old_path), str(new_path), "-o", str(out_path)])
    assert code == 0

def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["--version"])
    assert exc_info.value.code == 0
    assert "redline" in capsys.readouterr().out
```

Use pytest's built-in `capsys` fixture to assert on stdout/stderr content
(e.g. the exact error message for a missing file), rather than redirecting
`sys.stdout` manually.

---

## Test File Inventory

| File | What it covers |
|---|---|
| `test_text.py` | `normalize_whitespace`, `normalize_case`, `split_paragraphs`, `split_sentences`, `split_words` — confirms case is preserved by whitespace normalization and only folded by `normalize_case`. |
| `test_blocks.py` | `find_blocks`: exact duplicate detection, whitespace-only and case-only classification, adjacent-match merging, no-match case, moved-block / crossing-match resolution via the LIS drop-and-demote path, duplicate-paragraph position-order pairing. |
| `test_align.py` | `align_units` / `align_paragraphs`: identity short-circuit, small in-place edits staying a single `Edit`, totally unrelated text becoming insert+delete, heavy rewrites not crashing and not losing content, paragraph insertion/deletion, empty input. |
| `test_pipeline.py` | `compare_text` end-to-end: light edits mostly stay `Block`s, heavily revised documents don't crash, moved sections render without error, case-only changes are visible in the final HTML (regression test for the bug caught during implementation — see `redline/render.py`'s `_render_block`), pure insertions, and identical documents producing no `<ins>`/`<del>` at all. |
| `test_ingest_odt.py` | `from_odt`: paragraph and heading extraction, empty-paragraph skipping; `compare_odt` end-to-end. Uses `pytest.importorskip("odf")` so the suite still runs if `odfpy` isn't installed. |
| `test_cli.py` | `main()`: text comparison to stdout, `-o` writing to a file, format auto-detection for `.docx`/`.odt` from extension, `--format` overriding a missing/wrong extension, missing-file error message and exit code 1, `--version` exit code 0, unrecognized extension falling back to `"text"`. |

---

## Conventions

- **File names:** `test_<module>.py`, one file per `redline/` module (plus
  `test_pipeline.py` for end-to-end behavior).
- **Class grouping:** flat functions — the suite is small enough that
  `class Test...` grouping isn't needed. Introduce a class only if a
  file's test count grows past ~15-20 and natural groupings emerge.
- **Test naming:** `test_<behavior being verified>`, phrased as a claim
  about the code (`test_case_only_change_classified_not_hidden`), not a
  restatement of the function name.
- **Assertions:** plain `assert`, no `assertEqual`/`unittest`-style calls.
- **Expected exceptions:** not yet exercised in this suite (no test
  currently checks `from_docx`'s `ImportError` path). If adding one, use
  `with pytest.raises(ImportError):`.
- **No global state / cleanup:** every test is self-contained; nothing
  persists between tests, so no cleanup step is needed.
- **Parametrize rule:** not used yet. Reach for `@pytest.mark.parametrize`
  if a test starts repeating the same assertion shape over a list of
  near-identical inputs (e.g. testing several transform-ladder rungs) —
  don't introduce it preemptively.

---

## Common Imports

```python
# Phase 0
from redline.blocks import find_blocks, Block

# Phase 1
from redline.align import align_paragraphs, align_units, Identity, Edit, Insert, Delete

# Ingestion / normalization
from redline.text import normalize_whitespace, normalize_case, split_paragraphs, split_sentences, split_words
from redline.ingest import from_text, from_docx, Paragraph

# End to end
from redline.pipeline import compare_text, compare_docx, _compare_paragraphs

# CLI
from redline.cli import main
```

---

*Last updated: 2026-07-07 — added test_cli.py alongside the new CLI (redline/cli.py, redline/__main__.py, `redline` console script).*
