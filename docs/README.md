# redline

A lightweight Python library for comparing large, heavily-revised documents
and producing a legible redline — the same visual convention as legal
document comparison (underlined insertions, struck-through deletions) —
without the two failure modes that plague naive diff tools on big documents:
cascading false positives from a single early edit, and unreadable
word-salad ("Frankenstein") diffs on heavily-rewritten paragraphs.

## Why

Word's and LibreOffice Writer's built-in compare tools run a flat,
global diff over the whole document with no protection for text that
didn't change and no handling for moved sections — see `docs/API.md` for
the full design rationale. `redline` instead removes everything that's
provably unchanged first, then only runs the expensive comparison logic
on what's left.

## Quick Start

```bash
pip install python-docx   # only needed for .docx input
pip install odfpy         # only needed for .odt input
```

```python
from redline import compare_text

old = "The term shall be five years.\n\nBoth parties agree to arbitration."
new = "The term shall be seven years.\n\nBoth parties agree to arbitration."

html = compare_text(old, new)
open("redline.html", "w").write(html)
```

```python
from redline import compare_docx, compare_odt

html = compare_docx("contract_v1.docx", "contract_v2.docx")
html = compare_odt("contract_v1.odt", "contract_v2.odt")
```

### Command line

```bash
pip install -e .   # registers the `redline` command
redline contract_v1.docx contract_v2.docx -o redline.html
```

Format is auto-detected from the first file's extension (`.docx`/`.odt`/
anything else treated as plain text); pass `-f/--format` to override. Omit
`-o` to write HTML to stdout. See `docs/CHEATSHEET.md` for the full flag
reference, or run `redline --help`.

## Key Features

- **Two-phase design**: an exact/near-exact block-removal pass (Phase 0)
  sets aside unchanged paragraphs cheaply, before a recursive
  coarse-to-fine matcher (Phase 1) handles only the genuinely changed
  residue — paragraph → sentence → word, stopping as soon as `difflib`
  itself confirms the result will be legible.
- **Case changes are never silently hidden.** Whitespace and typographic
  noise (smart quotes, extra spaces) are treated as true non-changes;
  capitalization-only changes are still shown, because in a legal
  document `Agreement` vs. `agreement` can be meaningfully different.
- **Moved text degrades gracefully**: a relocated paragraph isn't forced
  into a false match — it renders as a clean delete-then-insert rather
  than a nonsensical local diff.
- **No heavy dependencies.** Standard library only, apart from
  `python-docx` for `.docx` input. No ML models, no embeddings.
- **Standalone HTML output** — one self-contained file, no server needed.
- **CLI included** — `redline old.docx new.docx -o out.html` for anyone who
  doesn't want to write Python; the library API is the same code underneath.

## Learn More

- `docs/API.md` — full reference, design rationale, and known limitations
- `docs/CHEATSHEET.md` — copy-paste operations and parameter reference
- `docs/workflows.md` — common end-to-end usage patterns
- `TEST_GUIDE.md` (project root) — test suite reference
