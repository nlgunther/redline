# redline — API Reference

## Design rationale (short version)

Two phases, run in order:

**Phase 0 — block removal (`blocks.py`).** A "block" is at least a
paragraph — boundaries come from document structure, not from discovering
extents with a sliding window, which is what removes the need for any
entropy-rate calibration: there's no minimum-length parameter to tune when
the unit is already the natural paragraph. Each paragraph is hashed under
an ordered ladder of transforms (exact text, then whitespace-normalized,
then case-folded); a match at a given rung tells you exactly what changed,
for the same cost as a single exact-match pass — no need to pay for
Phase 1's general matcher to rediscover something classifiable for free.
Whitespace/typographic differences are treated as true non-changes;
case differences are classified cheaply but still rendered as a visible
diff, since capitalization can be legally meaningful. Duplicate
paragraphs are matched in position order by default; if that would
produce a crossing (inconsistent) assignment, the conflicting match is
dropped back to "unmatched" via a longest-increasing-subsequence
resolution rather than guessing.

**Phase 1 — recursive matching (`align.py`).** Runs only on the residue
Phase 0 couldn't resolve. Once Phase 0's blocks are placed in document
order, they anchor both documents into the same spine — the hole between
block *i* and block *i+1* in document A corresponds, by construction, to
the hole between the same two blocks in document B, so no whole-document
candidate search is needed for that pairing. Within a hole, units are
aligned paragraph → sentence → word: at each level, a pair is accepted as
a legible diff once `difflib`'s own ratio clears a bar for that
granularity (staged behind `real_quick_ratio()`/`quick_ratio()` so the
full comparison only runs when it might matter); otherwise, if still
splittable, the pair is broken into the next level's units and
re-aligned via a small alignment DP scored by Jaccard word-overlap.
Rejected candidates become plain insertions/deletions instead of being
forced into a bad pairing.

## Module: `redline.text`

### `normalize_whitespace(text: str) -> str`
Collapses whitespace runs, normalizes smart quotes and non-breaking
spaces, applies Unicode NFC normalization. Does **not** fold case.

### `normalize_case(text: str) -> str`
`normalize_whitespace` followed by `.lower()`. Used only as a matching
key (Phase 0's "case" rung) — never used for rendered output.

### `split_paragraphs(text: str) -> list[str]`
Splits on blank lines.

### `split_sentences(text: str) -> list[str]`
Lightweight regex sentence splitter. Does not special-case abbreviations.

### `split_words(text: str) -> list[str]`
Whitespace tokenization; punctuation stays attached to the token.

## Module: `redline.hashing`

### `light_hash(text: str, digest_size: int = 8) -> bytes`
64-bit BLAKE2b digest. Non-cryptographic strength is intentional — see
the module docstring for the birthday-bound justification. Callers
verify true text equality on every hit, so hash strength only affects
lookup-table efficiency, not correctness.

## Module: `redline.blocks`

### `class Block`
Fields: `index_a: range`, `index_b: range`, `text_a: str`, `text_b: str`,
`transform: Literal["exact", "whitespace", "case"]`.

### `find_blocks(paras_a: list[str], paras_b: list[str]) -> tuple[list[Block], list[int], list[int]]`
Runs the transform ladder. Returns `(blocks, unmatched_a, unmatched_b)`,
where the unmatched lists are paragraph indices with no accepted match —
Phase 1's input.

**Example:**
```python
blocks, ua, ub = find_blocks(["Same.", "Old text."], ["Same.", "New text."])
# blocks[0].transform == "exact"; ua == [1]; ub == [1]
```

## Module: `redline.similarity`

### `jaccard(a: str, b: str) -> float`
Case-insensitive word-set overlap. Used only to score candidate pairings
in Phase 1 — never affects what's shown, only which sub-units get
recursed into together.

## Module: `redline.align`

### `class Identity`, `class Edit`, `class Insert`, `class Delete`
The four possible outputs of Phase 1. `Edit` carries both sides' text,
both sides' word-token tuples, and `difflib` opcodes.

### `align_paragraphs(paras_a: list[str], paras_b: list[str]) -> list`
Entry point for Phase 1: aligns the paragraph contents of one hole.

### `align_units(text_a: str, text_b: str, level: str) -> list`
Aligns a single unit pair at a given granularity (`"paragraph"`,
`"sentence"`, or `"word"`), recursing to finer granularity if the pair
isn't yet a legible diff and can still be split.

**Example:**
```python
align_units("The term is five years.", "The term is seven years.", "paragraph")
# -> [Edit(...)] with opcodes showing only "five"->"seven" changed
```

## Module: `redline.ingest`

### `class Paragraph`
Fields: `text: str`, `style: str = "Normal"`.

### `from_text(raw: str) -> list[Paragraph]`
Plain-text paragraph extraction.

### `from_docx(path) -> list[Paragraph]`
Requires `python-docx`. Raises `ImportError` with an install hint if
missing. Reads `document.paragraphs` only — table cells are not read.

### `from_odt(path) -> list[Paragraph]`
Requires `odfpy`. Raises `ImportError` with an install hint if missing.
Walks `document.text.childNodes`; only `<text:p>` and `<text:h>` elements
are read (tables and other element types are skipped, same scope
decision as `from_docx`). Heading elements become `style="Heading N"`
(from ODF's `outlinelevel` attribute) to match `from_docx`'s naming;
ordinary paragraphs carry ODF's own style name, or `"Normal"` if unset —
note this is *not* resolved to a human-readable name the way
`python-docx`'s `paragraph.style.name` is, since ODF style names are
whatever the authoring tool assigned (e.g. `"Standard"`, `"P1"`). Fine
for now since style still isn't wired through to rendering for either
format — see "Known limitations" below.

## Module: `redline.render`

### `render_html(items: list) -> str`
Renders a list of `Block`/`Identity`/`Edit`/`Insert`/`Delete` items to a
standalone HTML string (`<ins>`/`<del>`, inline CSS, no external assets).

## Module: `redline.pipeline`

### `compare_text(old_text: str, new_text: str) -> str`
### `compare_docx(old_path, new_path) -> str`
### `compare_odt(old_path, new_path) -> str`
Top-level entry points. Extract paragraphs, run Phase 0, walk the anchor
spine filling each hole via Phase 1, render to HTML.

## Module: `redline.cli`

Thin argument-parsing/IO layer over `redline.pipeline` — no comparison
logic lives here. Installed as the `redline` console script (via
`pyproject.toml`'s `[project.scripts]`) and also runnable as
`python -m redline` without installing.

### `main(argv: list[str] | None = None) -> int`
CLI entry point. Parses `argv` (defaults to `sys.argv[1:]` when `None`),
runs the comparison, writes the result, and returns a process exit code
instead of calling `sys.exit()` directly — this keeps it testable as a
plain function (see `tests/test_cli.py`).

**Arguments (parsed internally via `argparse`):**
- `old`, `new` (positional, `Path`): paths to the original and revised
  documents.
- `-o`, `--output` (`Path`, default `None`): write HTML here; `None` means
  stdout.
- `-f`, `--format` (`{"auto", "text", "docx", "odt"}`, default `"auto"`):
  input format. `"auto"` picks based on `old`'s file extension
  (`.docx` -> docx, `.odt` -> odt, anything else -> text) — see
  `_FORMAT_BY_SUFFIX`. Note detection only looks at `old`; pass this flag
  explicitly if `old`/`new` have different or missing extensions.
- `--version`: prints `redline <version>` and exits 0 (handled by
  `argparse`'s built-in `action="version"`, does not return to `main`).

**Returns:** `0` on success. `1` if the comparison couldn't be completed —
covers a missing file (checked explicitly up front, before either format's
reader runs, so the message is the same regardless of format), a missing
optional dependency (`ImportError` from `ingest.from_docx`/`from_odt`,
message includes the pip-install hint), or any other failure while reading
or comparing (corrupt document, encoding error, etc.) — all funneled
through one broad `except Exception` so the CLI never prints a raw
traceback to an end user.

Argument-parsing errors (`--help`, unknown flags, missing positionals) are
handled entirely by `argparse` and exit the process directly with code `2`
(or `0` for `--help`/`--version`) before `main`'s own try/except ever runs.

**Example:**
```python
from redline.cli import main

code = main(["contract_v1.docx", "contract_v2.docx", "-o", "redline.html"])
# -> 0, and redline.html now contains the comparison

code = main(["missing.docx", "contract_v2.docx"])
# -> 1, and "redline: no such file: missing.docx" is printed to stderr
```

## Known limitations (deliberate scope decisions, not oversights)

- **Formatting is out of scope.** Bold/italic/color/font are never
  compared; only text.
- **Tables are not handled.** `from_docx` skips table content entirely.
- **Headings render as plain paragraphs.** `Paragraph.style` is captured
  by `ingest.from_docx` but not yet threaded through Phase 0/1/render —
  a caller who wants heading-aware output needs to extend `Block` and the
  `Insert`/`Delete`/`Edit` dataclasses to carry style, and update
  `render.py` to emit `<h1>`-`<h6>` for heading styles. Left as a
  documented next step rather than done speculatively.
- **No native Word tracked-changes handling.** A `.docx` that already
  contains `<w:ins>`/`<w:del>` markup is read as if fully accepted;
  `python-docx`'s high-level API doesn't expose revision marks.
- **No explicit "moved from/to" annotation.** A relocated block renders
  as a clean delete + insert, not a labeled move. The anchor mechanism
  that would make move-labeling possible is already in place
  (`Block.index_a`/`index_b` gaps), but the renderer doesn't yet surface it.
- **Similarity scoring is plain Jaccard**, not the background-corrected
  (document-frequency-weighted) scoring discussed during design for
  telling apart near-duplicate boilerplate clauses. Simpler default for
  v1; swap `similarity.jaccard` for a fancier scorer if boilerplate
  collisions turn out to be a real problem in practice.
- **CLI format auto-detection only inspects `old`.** A mismatched pair
  (different or missing extensions) needs an explicit `--format`; the CLI
  doesn't try to reconcile disagreeing extensions or sniff file content.
