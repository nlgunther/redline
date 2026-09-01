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
candidate search is needed for that pairing. Within a hole, both sides'
paragraphs are flattened to a single tagged sentence sequence
(`align_paragraphs`/`_flatten_to_sentences`) and aligned at sentence
granularity across the *whole* hole — paragraph boundaries are not a
matching boundary at all, only metadata carried on each resulting item
and used afterward, by `_group_by_paragraph`, to regroup sentence-level
ops back into rendered paragraphs (see "Reworked 2026-07-21" below for
why). A sentence pair that isn't byte-identical is diffed directly at
word granularity (`align._diff_op`, one `SequenceMatcher` pass over both
sides' word tokens — see "2026-07-22" below for why there's no separate
word-level candidate-pairing step first). Candidate *sentence* pairing
within a hole (deciding which old sentence goes with which new one) still
uses a small alignment DP scored by `similarity.similarity_score` (a
threshold-gated blend of Jaccard and the overlap coefficient — see
below); as a special case, a hole with exactly one unit on each side pairs
unconditionally, skipping the DP and its acceptance threshold entirely —
see `align._align_sequence`. Rejected candidates become plain
insertions/deletions instead of being forced into a bad pairing.

**Reworked 2026-07-21** (see `docs/JOURNAL_2026-07-21.md`): Phase 1 used
to pair *paragraphs* first (one A-paragraph to one B-paragraph, via the
same DP), then recurse into sentences only within that one matched pair.
That silently assumed the two documents agree on where paragraph breaks
fall. A real case broke this assumption: an author split one paragraph
(two sentences on one line) into two paragraphs across a revision,
rewording only the first sentence. The single old paragraph could only be
paired with *one* of the two new paragraphs, so the other — despite
holding an entirely unchanged sentence — rendered as a disconnected
insert, and the matched pair rendered as a full-paragraph delete
alongside it. Flattening to sentences before matching (rather than
pairing paragraphs and recursing within pairs) fixes this: a paragraph
split or merge just becomes "the same sentence, tagged with a different
paragraph index on each side," which the existing identity-first
machinery in `align_units` already handles with no special-casing
needed. Empirically this also *tightens* diffs even in the common,
well-behaved case (no split/merge) — flattening straight to sentences
finds more exact sentence-level matches than a paragraph-level word-diff
does, since the latter only credits a shared span if it survives as a
contiguous run inside one big `SequenceMatcher` pass over the whole
paragraph.

**Later same day (still 2026-07-21):** `_align_sequence`'s DP is
order-preserving, so it can't represent a *crossing* correspondence — two
sentences that are simply swapped relative to each other (a local
reorder, both sides landing in the same Phase 1 hole) could lose to a
same-order-but-wrong pairing even though neither one's wording changed.
Fixed the same way Phase 0 already solves the equivalent paragraph-level
problem: `_exact_match_sentences` hashes every sentence in the hole and
matches by exact text, independent of position; `resolve_order` (now
shared with `blocks.py`, see `redline.ordering` below) keeps whichever
subset of those matches is mutually consistent. What's left goes through
the unchanged DP as before. The two results can't just be concatenated
into one pairs list, though — an exact match and a DP match can
themselves cross (that's what a real reorder *is*), and forcing them into
one monotonic list silently dropped the exact match that made the fix
work in the first place. So they're kept separate: exact matches render
directly as `Identity`, the DP's residual runs through the existing,
self-contained `_align_sequence`/`_interleave_tagged`, and only the
*rendered ops* are merged afterward (`_merge_in_paragraph_order`) —
ordered by rendered paragraph, since a genuine reorder has no single
correct fine-grained sentence order to recover, only a requirement that
same-paragraph content stay contiguous. This only catches *local*
reorders — a sentence relocated outside its original Phase 1 hole
entirely isn't visible to this pass; see "Phase 2" below for the fix.

**2026-07-22 — word-level candidate pairing removed.** `align_units` used
to have a third tier below "sentence not good enough as one edit": split
both sides into individual words and run the *same* DP-based pairing used
for sentences (`_align_sequence`, scored by `similarity_score`) to decide
which words to diff together before falling back to `_diff_op`. That
scorer treats its arguments as word sets, so comparing two single words
degenerates to "identical, or score zero" — any two non-identical words
are unlinkable candidates, so a run of several changed words shattered
into one `Delete`/`Insert` per word instead of one coherent replace span
(64 ops instead of 1, in a real example). `_diff_op` already produces a
clean multi-word replace span via its own `SequenceMatcher` pass — there
was nothing for word-level DP pairing to usefully decide once a sentence
wasn't good enough as a single edit, so `align_units` now calls
`_diff_op` directly in that case too, same as it always did once at the
(former) word floor. This removed `GRANULARITY_LADDER`, `GOOD_ENOUGH`,
`MIN_TOKENS`, `_at_floor`, `_clears_threshold`, `_split`, and `_interleave`
entirely — none had any remaining caller once the one transition that
used them (sentence → word) stopped needing a candidate-pairing step.

**2026-07-22 — Phase 2, cross-hole moves (`moves.py`).** The local-reorder
fix above only helps when both a sentence's old and new position land in
the *same* Phase 1 hole. A sentence or paragraph relocated far enough to
land in a *different* hole is invisible to it — each hole is matched
independently, so the content just survives as a plain orphaned `Delete`
on one side and a plain orphaned `Insert` on the other, with nothing
connecting them. New module `moves.py` runs once, after
`pipeline._stitch` assembles the whole document's `Block`/`ParagraphGroup`
sequence: it hashes every orphaned `Delete`/`Insert` across the *entire*
document (mirroring `blocks.py`'s own whole-document hash matching, just
applied to Phase 1's leftovers) and replaces any exact cross-match with a
`MovedAway`/`MovedHere` marker pair instead of an unrelated delete+insert.
Unlike `blocks.py`'s or `align.py`'s matching, no `resolve_order`/LIS
conflict resolution is needed here — those exist because their matches
feed a monotonic gap-filling walk, which this pass doesn't do; it splices
into an already-finalized rendering order, so a simple greedy match
("each `Delete` claims the earliest unclaimed `Insert` with equal text")
is sufficient, and ambiguous leftovers (e.g. more occurrences on one side
than the other) simply stay a plain `Delete`/`Insert`. Enabled by default
on all four `compare_*` entry points and the CLI; see `redline.moves` and
`redline.cli` below to disable it.

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

## Module: `redline.ordering`

Added 2026-07-21, promoted out of `blocks.py` when `align.py` needed the
same conflict-resolution logic at sentence granularity (see "Later same
day" above) — kept as a small standalone module rather than importing it
from `blocks.py` directly, so `align.py` (Phase 1) doesn't take on a
dependency on `blocks.py` (Phase 0) for something that isn't actually
paragraph-specific.

### `resolve_order(matches: list[tuple]) -> tuple[list[tuple], list[tuple]]`
Keeps the longest subsequence of `(a_index, b_index, ...)` match
candidates that's strictly increasing in both positions (patience-sorting
LIS on the second position after sorting by the first); returns
`(kept, dropped)`. Any elements after the first two in each tuple are
carried through unchanged (`blocks.py` uses a third element for the
transform name; `align.py`'s sentence-level matches don't need one).

**Example:**
```python
resolve_order([(0, 1), (1, 0)])
# -> ([(1, 0)], [(0, 1)])  -- these cross, so only one is kept
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
The four possible sentence/word-level ops Phase 1 produces. `Edit`
carries both sides' text, both sides' word-token tuples, and `difflib`
opcodes.

### `class ParagraphGroup`
Added 2026-07-21 alongside the sentence-flattening rework. Fields:
`items: list` (of `Identity`/`Edit`/`Insert`/`Delete`). One rendered
paragraph's worth of sentence-level ops — `align_paragraphs` now returns
`list[ParagraphGroup]` rather than a flat list of ops, since matching
happens purely at sentence granularity and paragraph shape has to be
reconstructed afterward (see `_group_by_paragraph`). `render.py` renders
one `ParagraphGroup` as a single `<p>` (or `<hN>`).

### `align_paragraphs(paras_a: list[str], paras_b: list[str]) -> list[ParagraphGroup]`
Entry point for Phase 1: flattens both sides' paragraphs to a tagged
sentence sequence (`_flatten_to_sentences`), aligns sentences across the
*whole* hole (paragraph membership plays no part in matching), then
regroups the resulting ops back into paragraphs via `_group_by_paragraph`
— by default following the *new* document's paragraph structure (the
convention track-changes tools use: show the result as it will look once
changes are accepted); a run of purely deleted sentences with no new-side
paragraph groups by the *old* document's structure instead, so a wholly-
removed paragraph still renders as one cohesive block.

**Example:**
```python
align_paragraphs(
    ["Shared opening sentence. Shared closing sentence."],
    ["Shared opening sentence, reworded.", "Shared closing sentence."],
)
# -> [ParagraphGroup([Edit(...)]), ParagraphGroup([Identity("Shared closing sentence.")])]
# -- the closing sentence is recognized as unchanged even though it
# moved to a different paragraph than its old one.
```

Internally (added the same day, see "Later same day" in the design
rationale above): `_align_flattened_sentences` runs `_exact_match_sentences`
(hash-based, position-independent) first, resolves conflicts among the
matches via `ordering.resolve_order`, then runs the existing
`_align_sequence`/`_interleave_tagged` on whatever's left. Exact matches
and the DP's residual are merged into final order by
`_merge_in_paragraph_order`, not by a shared pairs list — see that
function's docstring for why.

```python
align_paragraphs(
    ["Alpha stays the same. Beta stays the same too."],
    ["Beta stays the same too. Alpha stays the same."],
)
# -> both sentences render as Identity, even though they swapped order
```

### `align_units(text_a: str, text_b: str, level: str = "sentence") -> list`
Aligns a single unit pair: `Identity` if byte-identical, otherwise one
`Edit` via `_diff_op`'s word-level `SequenceMatcher` pass. `level` is
accepted for call-site compatibility (existing callers pass `"sentence"`)
but no longer changes behavior — see "2026-07-22" in the design rationale
above for why the word-level candidate-pairing tier this used to gate was
removed rather than fixed in place.

**Example:**
```python
align_units("The term is five years.", "The term is seven years.")
# -> [Edit(...)] with opcodes showing only "five"->"seven" changed
```

## Module: `redline.moves`

Added 2026-07-22 (Phase 2) — see "Phase 2, cross-hole moves" in the design
rationale above for the full reasoning.

### `class MovedAway`, `class MovedHere`
`MovedAway(text: str, direction: str)` marks a sentence's old position
once its exact match has been found elsewhere as a `MovedHere` — rendered
as a short direction marker, not the full text (the full text is shown
once, at the `MovedHere`). `MovedHere(text: str, direction: str)` is the
new position; `direction` is `"above"` or `"below"`, telling the reader
where the counterpart sits in rendered document order.

### `detect_moves(items: list) -> list`
Takes the full `Block`/`ParagraphGroup` sequence `pipeline._stitch`
produces, finds exact-content `Delete`/`Insert` pairs that survived both
phases unmatched only because they're in different holes, and returns a
new list with those replaced by `MovedAway`/`MovedHere` markers. Only
whole-sentence `Delete`/`Insert` ops are candidates — word-level ins/del
*inside* an `Edit` aren't visible at this granularity (a partially-
reworded sentence didn't "move"). Does not mutate `items`.

**Example:**
```python
detect_moves([
    ParagraphGroup([Delete("Charlie paragraph moved to the end.")]),
    Block(...),  # "Alpha paragraph unchanged." -- the sole anchor
    ParagraphGroup([Insert("Charlie paragraph moved to the end.")]),
])
# -> Charlie's Delete becomes MovedAway(..., "below");
#    its Insert becomes MovedHere(..., "above")
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
Renders a list of `Block`/`ParagraphGroup` items to a standalone HTML
string (`<ins>`/`<del>`, inline CSS, no external assets). Each item
renders as one `<p>` (or `<hN>`): a `ParagraphGroup`'s contained sentence
ops (`Identity`/`Edit`/`Insert`/`Delete`) render inline via `_render_inline`
and get wrapped in a single block-level tag once per group, not once per
sentence; `class='identity'` is added only when every item in the group
is `Identity` (nothing changed anywhere in that paragraph).

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

`MovedAway`/`MovedHere` (added 2026-07-22, see `redline.moves`) render via
two more `_render_inline` dispatch arms: `MovedAway` as
`<span class='moved'>{moved above|below}</span>` (no sentence text —
it's shown once, at the `MovedHere`); `MovedHere` as
`<span class='moved'>{moved from above|below} <text></span>`. Both use a
new `.moved` CSS class (amber/beige, distinct from `<ins>`/`<del>`'s
green/red) so a relocation reads as "this moved," not "this changed."

## Module: `redline.pipeline`

### `compare_text(old_text: str, new_text: str, detect_moves: bool = True) -> str`
### `compare_docx(old_path, new_path, detect_moves: bool = True) -> str`
### `compare_odt(old_path, new_path, detect_moves: bool = True) -> str`
### `compare_pdf(old_path, new_path, detect_moves: bool = True) -> str`
Top-level entry points. Extract paragraphs, run Phase 0, walk the anchor
spine filling each hole via Phase 1, run `moves.detect_moves` (Phase 2)
over the assembled result unless `detect_moves=False`, render to HTML.

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
- `-f`, `--format` (`{"auto", "text", "docx", "odt", "pdf"}`, default
  `"auto"`): input format. `"auto"` picks based on `old`'s file extension
  (`.docx` -> docx, `.odt` -> odt, `.pdf` -> pdf, anything else -> text) —
  see `_FORMAT_BY_SUFFIX`. Note detection only looks at `old`; pass this
  flag explicitly if `old`/`new` have different or missing extensions.
- `--suppress-moves` (flag, default off): disables Phase 2 (added
  2026-07-22, see `redline.moves`) — a relocated sentence renders as a
  plain delete+insert instead of a labeled `{moved above}`/`{moved below}`
  pair. Threaded through as `detect_moves=False` to whichever `compare_*`
  function runs.
- `--version`: prints `redline <version>` and exits 0 (handled by
  `argparse`'s built-in `action="version"`, does not return to `main`).

**Returns:** `0` on success. `1` if the comparison couldn't be completed —
covers a missing file (checked explicitly up front, before either format's
reader runs, so the message is the same regardless of format), a missing
optional dependency (`ImportError` from `ingest.from_docx`/`from_odt`,
message includes the pip-install hint), or any other failure while reading
or comparing (corrupt document, an unreadable text-file encoding, etc.) —
all funneled through one broad `except Exception` so the CLI never prints a
raw traceback to an end user.

For the text format specifically, "unreadable encoding" is now a narrow
case: `_compare` reads `old`/`new` via `_read_text_file`, which tries
UTF-8 (BOM-tolerant, via `utf-8-sig`) and then falls back to cp1252
(Windows' historical default single-byte encoding) before giving up —
added because a `.txt` saved by Word or Notepad on Windows is often
cp1252, not UTF-8, and previously any such file crashed with a raw
`UnicodeDecodeError` (just a byte offset, no filename) instead of being
read. Only a file that decodes as neither (e.g. actually binary) still
reaches exit code 1, and does so with a clear message naming the file and
both encodings tried.

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
- **Move detection is exact-text-only, and doesn't merge adjacent moved
  sentences into one annotation.** As of 2026-07-22 (`moves.py`, Phase 2),
  a relocated sentence — local reorder within one hole, or a full
  cross-hole relocation — is recognized and labeled `{moved above}`/
  `{moved below}` rather than rendered as an unrelated delete+insert (see
  the design rationale above). Two real limitations remain: (1) the match
  is exact-text only, same as everywhere else in this codebase — a
  sentence that moved *and* was reworded isn't recognized as a move at
  all, just an ordinary edit in one place and an ordinary insert/delete in
  another; (2) if several consecutive sentences relocated together as a
  block, each one gets its own separate `{moved}` marker rather than one
  annotation for the whole block — correct, just visually noisier than
  ideal. `--suppress-moves` (CLI) / `detect_moves=False` (library) turns
  the whole pass off if the marker noise isn't wanted.
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
