# redline — Cheatsheet

## Common Operations

### Compare plain text
```python
from redline import compare_text
html = compare_text(old_text, new_text)
```

### Compare .docx files
```python
from redline import compare_docx
html = compare_docx("v1.docx", "v2.docx")
```

### Compare .odt files
```python
from redline import compare_odt
html = compare_odt("v1.odt", "v2.odt")
```

### Just find unchanged blocks (Phase 0 only)
```python
from redline.blocks import find_blocks
blocks, unmatched_a, unmatched_b = find_blocks(paragraphs_a, paragraphs_b)
for b in blocks:
    print(b.transform, b.index_a, b.index_b)  # "exact" | "whitespace" | "case"
```

### Diff two paragraphs directly (Phase 1 only)
```python
from redline.align import align_paragraphs
ops = align_paragraphs(["Old paragraph text."], ["New paragraph text."])
```

### Compare from the command line
```bash
redline old.docx new.docx -o redline.html   # auto-detects format from OLD's extension
redline old.txt new.txt                     # writes HTML to stdout
redline old.rtf new.rtf --format text -o out.html   # force a format
python -m redline old.docx new.docx -o out.html     # without installing the console script
```

## CLI Flag Reference

| Flag | Purpose |
|---|---|
| `old`, `new` (positional) | Paths to the original and revised documents |
| `-o`, `--output PATH` | Write HTML here; default is stdout |
| `-f`, `--format {auto,text,docx,odt}` | Input format; default `auto` (from `old`'s extension) |
| `--version` | Print version and exit |
| `-h`, `--help` | Print usage and exit |

Exit codes: `0` success, `1` comparison failed (missing file, missing
optional dependency, unreadable document), `2` bad arguments (from
`argparse` itself).

## Parameter / Constant Reference

| Name | Location | Default | Purpose |
|---|---|---|---|
| `TRANSFORM_LADDER` | `blocks.py` | exact → whitespace → case | Phase 0 rungs, strictest first |
| `GRANULARITY_LADDER` | `align.py` | paragraph → sentence → word | Phase 1 recursion levels |
| `GOOD_ENOUGH` | `align.py` | `{paragraph: 0.35, sentence: 0.55}` | difflib ratio needed to stop recursing |
| `MIN_TOKENS` | `align.py` | `6` | floor below which recursion always stops |
| `PAIR_THRESHOLD` | `align.py` | `0.15` | minimum Jaccard score to accept a candidate pairing |
| `digest_size` | `hashing.light_hash` | `8` (64-bit) | hash width for Phase 0's lookup table |

## Gotchas

- **Case changes are shown, whitespace changes are not.** This is
  deliberate — see `docs/README.md` "Why". If you want case folded away
  too, you'd change `render._render_block` to also skip `"case"`.
- **`compare_docx` requires `python-docx`; `compare_odt` requires `odfpy`.**
  Neither is a hard dependency of the package; each is only imported
  inside its own `ingest.from_*` function, with a clear `ImportError` if
  missing.
- **ODT paragraph style names aren't human-readable** the way docx's are
  (`"Standard"` / `"P1"` instead of `"Normal"`) — cosmetic only, since
  style isn't compared or rendered yet either way.
- **Headings render as plain paragraphs today.** `Paragraph.style` is
  extracted but not yet threaded through to the renderer — see
  `docs/API.md` "Known limitations".
- **Tables are not handled.** `from_docx` reads `document.paragraphs`
  only; table cells are currently skipped entirely, not compared.
- **Sentence splitting is regex-based**, not a full NLP sentence
  tokenizer — it will occasionally mis-split on abbreviations. Deliberate
  choice to avoid a heavy dependency like spaCy.
- **CLI format auto-detection only looks at `old`'s extension.** If `old`
  and `new` have different extensions (e.g. comparing a `.txt` draft
  against a `.docx` final), pass `--format` explicitly rather than relying
  on auto-detect.
- **Extension-less files always need `--format`.** Auto-detect falls back
  to `"text"` for any extension it doesn't recognize, which will silently
  misread a `.docx`/`.odt` file that's missing its extension.

## Full reference

See `docs/API.md`.
