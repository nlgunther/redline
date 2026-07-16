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
re-aligned via a small alignment DP scored by `similarity.similarity_score`
(a threshold-gated blend of Jaccard and the overlap coefficient — see
below). As a special case, a hole with exactly one unit on each side pairs
unconditionally, skipping the DP and its acceptance threshold entirely —
see `align._align_sequence`. Rejected candidates become plain
insertions/deletions instead of being forced into a bad pairing.

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

### `similarity_score(a: str, b: str) -> float`
Case-insensitive word-set similarity for candidate pairing. Below
`PAIR_OVERLAP_THRESHOLD` (default `0.5`, measured as the overlap
coefficient `|A∩B|/min(|A|,|B|)`), this is plain Jaccard
(`|A∩B|/|A∪B|`). Above the threshold, it ramps linearly from Jaccard up
to `1.0` as overlap approaches `1.0` — this fixes plain Jaccard's
systematic under-scoring of genuine containment (a short unit fully
absorbed into a longer edited one), without inflating scores for short,
unrelated text that coincidentally shares words. Used only to score
candidate pairings in Phase 1 — never affects what's shown, only which
sub-units get recursed into together.

**Example:**
```python
similarity_score("the tenant shall maintain the property",
                  "the tenant shall maintain the property and grounds in good repair")
# -> ~1.0 (near-total containment, versus ~0.19 for plain Jaccard)
```

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

### `from_pdf(path) -> list[Paragraph]`
Requires the `readers` package with its `pdf` extra (`pypdf`). Raises
`ImportError` (with an install hint) if `readers` isn't installed at all,
or if `readers` is installed but `pypdf` isn't; raises `ValueError` for
any other unreadable-PDF outcome (not found, corrupt, empty, permission
denied). Extraction and section recovery are both delegated to `readers`
(`read_file` + `split_into_sections`) — see `readers/JOURNAL_2026-07-12.md`
("Option A") for why this lives in the shared package rather than
`redline`, and why it uses `split_into_sections` rather than
`recover_paragraphs` directly (ordinary paragraph boundaries have no
reliable signal in flat PDF text; two revisions of the same document can
merge that ambiguous text differently, which used to render near-
identical paragraphs as a full delete+insert instead of a word-level
edit). Each detected heading becomes its own `Paragraph` with
`style=f"Heading {level}"` (level is text-derived — a section-number
prefix like "2.3" gives real depth, an unnumbered heading defaults to 1;
pypdf exposes no font-size signal); the (usually large) body of ordinary
text between headings is one `Paragraph` with `style="Normal"`, left for
`redline`'s own sentence-level recursive alignment to diff rather than
split further here.

## Module: `redline.render`

### `render_html(items: list, style_by_text: dict | None = None) -> str`
Renders a list of `Block`/`Identity`/`Edit`/`Insert`/`Delete` items to a
standalone HTML string (`<ins>`/`<del>`, inline CSS, no external assets).

`style_by_text` (added 2026-07-12, see `readers/JOURNAL_2026-07-12.md`
"Option A"): an optional map of exact paragraph text → style (e.g.
`"Heading 1"`), used to render that paragraph as `<h1>`-`<h6>` instead of
`<p>`. Looked up per rendered item via the internal `_tag_for(text,
style_by_text)` helper — for `Edit`, tries `text_a` then falls back to
`text_b`. Deliberately text-keyed rather than adding a style field to
`Block`/`Identity`/`Edit`/`Insert`/`Delete` themselves: every one of
those already carries the paragraph text verbatim, so a lookup gets the
same result without widening those dataclasses' shape. Currently only
`pipeline.compare_pdf` builds and passes a `style_by_text`; every other
`compare_*` still renders plain `<p>` for every paragraph.

Word-level "replace" spans with mismatched token counts get a
character-level diff on the joined spans if either `SequenceMatcher.ratio()`
clears `WORD_CHAR_THRESHOLD`, or the shorter side's words (punctuation
stripped) are all found in the longer side (`_shorter_side_is_contained`)
— the latter catches cases a raw character ratio misses because it's
penalized by pure length disparity (e.g. a short token followed by a much
longer appended clause that still contains the original word).

## Module: `redline.pipeline`

### `compare_text(old_text: str, new_text: str) -> str`
### `compare_docx(old_path, new_path) -> str`
### `compare_odt(old_path, new_path) -> str`
### `compare_pdf(old_path, new_path) -> str`
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
- **Headings render as `<h1>`-`<h6>` only for the PDF path.**
  `compare_pdf` builds a `style_by_text` map and threads it through
  `render_html` (see `render_html`'s entry above). `Paragraph.style` is
  also captured by `ingest.from_docx`/`from_odt`, but `compare_docx`/
  `compare_odt` don't yet build or pass a `style_by_text` map, so headings
  from those formats still render as plain `<p>` — a natural, not-yet-done
  follow-up (the plumbing already exists; it just isn't wired for those
  two entry points).
- **No native Word tracked-changes handling.** A `.docx` that already
  contains `<w:ins>`/`<w:del>` markup is read as if fully accepted;
  `python-docx`'s high-level API doesn't expose revision marks.
- **No explicit "moved from/to" annotation.** A relocated block renders
  as a clean delete + insert, not a labeled move. The anchor mechanism
  that would make move-labeling possible is already in place
  (`Block.index_a`/`index_b` gaps), but the renderer doesn't yet surface it.
- **Similarity scoring is a Jaccard/overlap-coefficient blend**, not the
  background-corrected (document-frequency-weighted) scoring discussed
  during design for telling apart near-duplicate boilerplate clauses.
  Simpler default for v1; swap `similarity.similarity_score` for a
  fancier scorer if boilerplate collisions turn out to be a real problem
  in practice.
- **CLI format auto-detection only inspects `old`.** A mismatched pair
  (different or missing extensions) needs an explicit `--format`; the CLI
  doesn't try to reconcile disagreeing extensions or sniff file content.
- **PDF section boundaries are a best-effort heuristic, not exact.**
  `from_pdf` relies on `readers.split_into_sections` (itself built on
  `readers.recover_paragraphs`), which infers headings from line-ending
  punctuation and heading-like lines (a text heuristic — no font-size
  signal, since pypdf's extracted text carries no such information). It
  can occasionally mis-detect a heading, and ordinary (non-heading)
  paragraph structure within a section's body is intentionally *not*
  preserved — see `readers/segment.py`'s docstring and
  `readers/JOURNAL_2026-07-12.md` ("Option A") for why. pypdf also loses
  some inter-word spacing around inline math/subscripts in certain font
  encodings — a pass-through limitation, not something `redline` can
  correct.
