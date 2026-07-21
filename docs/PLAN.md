# redline — Update Plan

Written after a long design session covering a rendering bug, two rounds of
independent architecture review (Opus), and several of Ken's own proposals.
This is the synthesized roadmap — what's decided, what's rejected, and in
what order the rest should be built. Phase A and the shape-based/scoring
parts of Phase D have since shipped (see "Shipped" below); Phases B, C, E
and the rest of D remain unimplemented. This file is the plan, not a
changelog — see `KT.md` for a chronological record.

---

## 1. Decisions ledger

### Shipped

- **Same-token-count character-level diff.** `render.py`'s `_render_replace`/
  `_render_token_pair` (`WORD_CHAR_THRESHOLD = 0.5`): a word-level "replace"
  opcode with equal token counts on both sides now gets a nested
  character-level diff instead of a whole-word swap. Fixes the reported bug
  (`technology".` vs `technology"` marking the whole word instead of just the
  punctuation).
- **Different-token-count character-level diff.** `_render_replace`'s
  different-token-count branch now attempts the same character-level diff
  on the *joined* spans (same threshold, via the shared `_char_diff_html`
  helper) before falling back to a whole-span swap. Verified against the
  motivating case (`'This statement is incorrect.'` → `'...now clearly
  incorrect"'` marks only the two inserted words and the punctuation).
  Render-only change, strictly backward-compatible below threshold, no data
  model change.
- **1-vs-1 forced pairing.** `align.py::_align_sequence` now pairs a hole's
  units unconditionally when each side has exactly one candidate, skipping
  `PAIR_THRESHOLD` entirely. Fixes the bug where two totally dissimilar sole
  occupants of a hole rendered as a disconnected `Delete`+`Insert` instead of
  one `Edit`.
- **Containment-aware similarity score.** `similarity.py::jaccard()` renamed
  to `similarity_score()` (honest naming — it's no longer plain Jaccard) and
  reimplemented as the threshold-gated Jaccard/overlap-coefficient blend
  described below (default `T = 0.5`). All `align.py` call sites updated.
  Fixes plain Jaccard's under-scoring of genuine containment without
  inflating false positives on short/unrelated text.

All four tested (`tests/test_render.py`, `tests/test_align.py`,
`tests/test_similarity.py` — 57 tests total), docs updated
(`docs/API.md`, `docs/CHEATSHEET.md`, `TEST_GUIDE.md`), manifest
regenerated (bundle `a10d64e3b307b8cfcdf540d4`, all passing,
`verify_install.py` clean).

- **Follow-up fix: word-level containment check for the char-diff gate.**
  The different-token-count char-diff item above had a residual bug: a
  short old token followed by a much longer new phrase that still opened
  with the same word (e.g. `'incorrect.'` -> `'incorrect as applied to
  the homomorphic encryption scheme.'`) still fell back to a whole-span
  swap, because `SequenceMatcher.ratio()` on the joined spans is a
  character-level ratio that penalizes size disparity the same way plain
  Jaccard did — the exact bug just fixed in `similarity.py`, one layer
  down. Fixed by adding `render.py::_shorter_side_is_contained`, which
  checks word-level (not character-level) containment after stripping
  punctuation, and OR-ing it into `_render_replace`'s existing
  `WORD_CHAR_THRESHOLD` gate. A raw character-level containment check was
  tried and rejected first: verified empirically that it also scores
  `'cat'` as 1.0 "contained" in `'category stuff here'`, a false positive
  from a coincidental substring match rather than a real shared word.
  Tested (4 new tests in `tests/test_render.py`, 61 tests total), docs
  updated, manifest regenerated (bundle `76ed3ca0edb7fe66d6ece6e4`).

### Designed, verified, not yet in code

(none currently — the previously-listed different-token-count char-diff
item shipped this pass; see "Shipped" above)

### Adopted direction, not yet built

- **Semantic IR.** Replace `render.py`'s direct flat-list-to-HTML walk with
  a small in-memory node tree (paragraph/table/run/moved, not
  OOXML/ODF-shaped — those two formats track changes structurally
  differently, so mirroring either makes the other harder). `render.py`
  becomes the first of several converters reading that tree; docx/odt
  converters become additive later work instead of parallel rewrites of the
  diff engine. `Identity`/`Edit`/`Insert`/`Delete` in `align.py` are already
  close to the right node shape — what's missing is nesting and a `Moved`
  node carrying paired old/new identity. XML serialization (stdlib
  `xml.etree.ElementTree`) is a thin adapter over the tree, not the tree
  itself — build the node model first.
- **Move detection, generalized across granularity.** `blocks.py`'s
  `_resolve_order` already computes the paragraph-level moved set for free —
  matches it drops specifically because they'd cross another kept match are,
  by definition, moved paragraphs. The same mechanism generalizes one level
  down: inside a hole, a sentence-level exact match whose position is
  out-of-order relative to the rest of that hole's content is a sentence
  move, not a silent anchor. One mechanism (`blocks.py`'s hash + crossing
  check), reused at both granularities, rather than two bespoke ones.
  Rendered as paired `MovedOut`/`MovedIn` nodes with cross-reference labels
  ("[Moved from ¶12]"/"[Moved to ¶18]") at both positions. Known caveat:
  genuinely duplicated boilerplate can only get *some* consistent pairing;
  occasional mislabeling of a coincidental duplicate as "moved" is an
  inherent, pre-existing ambiguity, not a new defect.
- **Performance fix for the O(n·m) alignment DP, as a hybrid.** Real
  benchmarks: light-edit documents scale linearly (50k paragraphs, 2.3s);
  heavily-revised or near-duplicate-heavy documents scale super-linearly
  (8,000 fully-changed paragraphs, 27s), because Phase 0 finds no anchors
  and the whole document collapses into one hole for Phase 1's DP. Fix:
  add a sentence-level exact-match pre-pass *inside* a hole (reusing
  `blocks.py`'s hash+LIS machinery at sentence granularity, combined with
  the move-detection generalization above) to shrink a hole into small
  residual sub-holes before the DP ever runs. **Keep `similarity.py`'s DP
  as the fallback** for whatever has no exact sub-match — removing it
  entirely was tried on paper and rejected (see below): it reintroduces
  word-salad output on heavily reworded-but-related paragraphs, one of the
  two failure modes this project exists to avoid. **Note:** the shape-based
  fast path (1-vs-1) and the containment-aware scoring upgrade originally
  scoped as part of this Phase D item have already shipped — see "Shipped"
  above and Phase D below for what remains (the sentence-level pre-pass and
  the 1-vs-M/N-vs-1/N-vs-M≥2 shapes).
- **Table diffing.** Treat each table row as a paragraph-equivalent unit
  (cells joined by a delimiter) so the existing paragraph pipeline handles
  row match/insert/delete/move for free once the move-detection work above
  lands; add a `"cell"` rung to `align.py`'s granularity ladder between row
  and sentence. Explicitly **out of scope**: column-structure changes
  (inserted/deleted columns, merged cells — row-flattening can't represent
  columns at all) and embedded Excel/OLE objects (a materially separate
  problem — not something `python-docx` parses). "Reinsert into the
  objects" is easy for HTML output; it is a much bigger, separate lift for
  native docx tracked-changes output (see below).

### Explicitly rejected

- **Unifying Phase 0 and Phase 1 into one recursive `difflib.SequenceMatcher`
  engine**, treating whole paragraphs (then sentences) as opaque elements
  compared by strict equality. Rejected on technical grounds, not taste:
  `SequenceMatcher` only matches by strict equality, so on the two workloads
  that are actually slow (heavy revision, near-duplicate boilerplate) it
  finds zero matches and still needs the same fuzzy pairing underneath — the
  cost relocates, it doesn't disappear. Parked exception: narrowly
  reconsidering `SequenceMatcher` just inside `_resolve_order`, for
  duplicate-boilerplate disambiguation specifically, *if* a real (not
  theoretical) misassignment bug ever shows up in practice. Not scheduled.
- **Pure recursive exact-match extraction with no fuzzy-pairing fallback**
  (the "difflib at every granularity, paragraphs as characters" idea in its
  unhedged form). Rejected for the same underlying reason: removing the
  Jaccard DP entirely, rather than keeping it as a fallback, produces
  whole-hole word salad the instant a hole contains no exact sub-match
  anywhere — exactly the case of a paragraph rewritten sentence-by-sentence
  with shared vocabulary but zero verbatim survival. The *anchor-finding*
  half of this idea was kept (see the performance-fix hybrid above); the
  *replace-the-DP* half was not.

### Flagged, not designed at all yet

- **Native Word tracked-changes output** (real OOXML `<w:ins>`/`<w:del>`
  elements in an actual `.docx`, versus today's read-only HTML). Identified
  this session as redline's single biggest gap versus commercial legal
  redlining tools (Litera/Workshare Compare, Draftable). The semantic IR is
  a prerequisite (a converter needs a tree to read), but the IR does not
  make this free — the XML→OOXML mapping itself is separate, substantial,
  undesigned work. Treat as its own future initiative once the IR is
  stable; not sequenced further in this plan.
- **`.odt` output**, same status as above.

---

## 2. Roadmap

Ordered by dependency, not just priority — later phases build on earlier
ones except where noted otherwise.

### Phase A — Land the char-diff generalization — **DONE**
- Implemented the different-token-count branch in `render.py::_render_replace`.
- Added tests to `tests/test_render.py` for the different-count-clears-threshold
  case; confirmed the existing sub-threshold whole-span test is unchanged.
- Regenerated `MANIFEST.txt`.

### Phase B — Semantic IR foundation
Depends on: nothing structurally, but should land before C/E per Opus's
sequencing argument (both need nesting/cross-referencing a flat list can't
represent well).
- Define the node model: a shallow `Document` tree of block-level nodes
  (paragraph, later table/row/cell), each containing the existing
  `Identity`/`Edit`/`Insert`/`Delete` leaf content plus a new `Moved` node
  with paired identity.
- Promote `pipeline.py`'s flat op-list construction into building this tree
  instead. Phase 0/1 emit nodes rather than appending to a list.
- Rewrite `render.py` as the first tree-to-HTML converter. **Regression
  gate: existing test suite output must be byte-identical** for all
  non-move, non-table cases — this is a refactor of the rendering boundary,
  not a behavior change, and the current 45+ tests are the safety net.
- Add XML serialization as a thin adapter over the node tree (stdlib
  `xml.etree.ElementTree`), since Ken specifically wants XML as an available
  output, not just an internal detail.

### Phase C — Move detection (paragraph + sentence, unified mechanism)
Depends on: B (moves are represented as IR nodes with paired identity from
the start, not retrofitted onto a flat list).
- Expose `blocks.py::_resolve_order`'s dropped/crossing matches as a `moved`
  list from `find_blocks`, instead of folding them into `unmatched`.
- Generalize the same hash + crossing-check mechanism to run inside a hole
  at sentence granularity (this step is shared with Phase D — see below).
- Render `Moved` IR nodes with cross-reference labels at both positions.
- Document the duplicate-boilerplate mislabeling caveat in `docs/API.md`
  "Known limitations" rather than trying to eliminate it.

### Phase D — Performance fix (combined with C)
Depends on: the same sentence-level hash+crossing mechanism Phase C builds;
implemented together, not sequentially, since they share code. **The two
sub-items below are done; the rest of Phase D (sentence-level pre-pass,
remaining shapes, benchmark) is not.**

- Sentence-level exact-match pre-pass inside `_fill_hole`, splitting a large
  hole into small residual sub-holes before `_align_sequence`'s DP runs.
  **Not done** — still depends on Phase C's hash+crossing mechanism.
- **Shape-based fast paths in `_align_sequence`, checked before the DP runs**:
  for a hole/sub-hole with N old units and M new units, (a) N=0 or M=0 needs
  no pairing at all — already correct, the DP is a no-op when either
  dimension is 0; (b) **N=1, M=1 always pairs unconditionally — DONE.**
  `_align_sequence` now special-cases this before the DP runs, regardless of
  content similarity. (c) 1-vs-M or N-vs-1 (singleton facing several) and
  N-vs-M with both ≥2 are the only shapes that still need real pairing
  logic — reserved for the DP, unchanged.
- Keep `similarity.py`'s DP as the fallback path for sub-holes with no exact
  anchor and an ambiguous shape — do not remove it.
- **Upgrade `similarity.py::jaccard` to a containment-aware score — DONE.**
  Renamed to `similarity_score()`, used both for `_align_sequence`'s DP and
  the `PAIR_THRESHOLD` acceptance check. Motivating case: a short paragraph
  fully contained in a longer, edited one scored 0.19 under plain Jaccard,
  barely above `PAIR_THRESHOLD` — fixed via a threshold-gated blend of
  Jaccard (`J`) and the overlap coefficient (`O = |A∩B|/min(|A|,|B|)`):
  below `T` (default **0.5**), score is plain `J`; above `T`, ramps linearly
  to `1.0` as `O` approaches `1`: `score = J + w*(1-J)`,
  `w = (O-T)/(1-T)`. Verified to reproduce plain Jaccard on an
  unrelated-text control (0.133, unchanged) while boosting genuine
  near-containment (0.8 overlap → ~0.68, versus 0.19 unblended). **Future
  option, not adopted:** a single-exponent power-law blend
  (`score = J*(1-O**e) + O**(e+1)`) was rejected as a *replacement* for the
  threshold — the exponent can't independently tune false-positive
  suppression vs. true-positive preservation, since both live on the same
  curve. Worth revisiting only as a curvature parameter for the ramp
  *between* `T` and `1`, not as a way to drop `T`.
- Rebuild the throwaway benchmark script as a proper, committed benchmark
  (not a pytest-gated regression test — timing assertions are flaky — but a
  script future sessions can rerun) and confirm the 8,000-paragraph/heavy-edit
  case drops well below the current 27s. **Not done** — still blocked on the
  sentence-level pre-pass above; the two shipped fast-path/scoring items
  don't by themselves fix the O(n·m) collapse.

### Phase E — Table diffing
Depends on: B (table nesting needs the IR) and ideally C (row moves should
reuse the same move mechanism rather than a bespoke one).
- Extend `ingest.py` to extract table structure (`python-docx` tables,
  `odfpy` tables) as `Table`/`Row`/`Cell` IR nodes, with each row also
  exposed as a paragraph-equivalent (cells joined by a delimiter) to the
  existing pipeline.
- Add a `"cell"` rung to `align.py`'s `GRANULARITY_LADDER` between row and
  sentence.
- New render path: `Table` IR node → HTML `<table>`.
- Document column-structure changes and embedded Excel/OLE objects as
  explicit non-goals in `docs/API.md`, not silent gaps.

### Not scheduled
Native docx/odt tracked-changes output — flagged as valuable, undesigned;
worth its own planning pass once B–E are stable, not detailed here.

---

## 3. Cross-cutting housekeeping (roll into whichever phase touches the file)

- `docs/API.md`, `docs/CHEATSHEET.md`, `docs/workflows.md`: update as each
  phase lands (new public surface: `moved` from `find_blocks`, the IR node
  types if any become public, the `"cell"` granularity rung).
- `TEST_GUIDE.md`: add entries for any new test files.
- `KT.md`: keep the Recent Decisions / Open Questions sections current as
  phases complete — several of that file's current open questions are
  exactly the phases above.
- Initial git commit is still outstanding, independent of all of this.
