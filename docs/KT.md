# KT — redline

> Last updated: 2026-07-08T22:48:03Z | Trigger: manual | Staleness: Fresh

---

## 1. Project Overview

`redline` is a lightweight, dependency-minimal Python package that redlines
large, heavily-revised documents (legal contracts especially) — producing
`<ins>`/`<del>` HTML output like Word's "Compare Documents," but designed to
avoid two failure modes Word/LibreOffice Writer both have: cascading false
positives from one early edit, and unreadable word-salad diffs on
heavily-rewritten paragraphs. Supports `.txt`, `.docx`, and `.odt` input,
and has both a library API and a command-line interface.

Current status: **Active Development**. Core library, all three input
formats, and the CLI are implemented and tested (61 tests passing). A prior
session shifted from bug-fixing into forward-looking architecture (move
detection, table support, a semantic IR) and produced `PLAN.md` as the
synthesized roadmap. This session landed the three fully-specified,
low-risk items from that plan's "Phase A" / early "Phase D" scope: the
different-token-count character-diff generalization, the 1-vs-1
forced-pairing fix, and the containment-aware similarity score. The larger
architecture items (semantic IR, move detection, table diffing) remain
unimplemented — see Open Questions and `PLAN.md`.

## 2. Goals & Constraints

**Goals:**
- Two-phase comparison: cheap exact/near-exact block removal first (Phase
  0), then a recursive coarse-to-fine matcher only on genuinely changed
  residue (Phase 1).
- Support `.txt`, `.docx`, and `.odt` as input formats.
- Produce standalone, self-contained HTML redline output today; a
  semantic IR with additional output converters (docx, odt) is the
  leading candidate for where this goes next (see `PLAN.md`).
- Provide both a Python library API (`compare_text`/`compare_docx`/`compare_odt`)
  and a CLI (`redline` console script / `python -m redline`).

**Constraints:**
- No heavy dependencies — standard library only, apart from optional
  `python-docx` (.docx) and `odfpy` (.odt), each imported lazily inside its
  own ingest function. Any XML IR work should stay on stdlib
  `xml.etree.ElementTree`, not add a dependency.
- Code quality per `ken-code-quality` skill: small functions (<30 lines
  typical), files <600 lines, plan-before-code for non-trivial features,
  honest naming (this is why `similarity.py::jaccard` was renamed to
  `similarity_score` this session — it stopped being plain Jaccard).
- Documentation per `code-documentation-writing` skill: every module needs
  `docs/README.md`, `docs/CHEATSHEET.md`, `docs/API.md`, `docs/workflows.md`
  coverage, plus `TEST_GUIDE.md` for the test suite.
- Explicit, standing preference (Ken): calibrate engineering effort to
  actual likelihood of the problem occurring — elegant generalizations are
  not adopted just for their elegance. This is why the paragraph-level
  `SequenceMatcher` unification (see `PLAN.md` "Explicitly rejected") was
  rejected despite being a genuinely clever idea, and why this session
  scoped down to only the fully-specified, low-risk plan items rather than
  attempting the larger phases in the same pass.

**Non-goals (documented in `docs/API.md` "Known limitations"):**
- Table extraction/comparison (`.docx`/`.odt` tables are skipped entirely)
  — a concrete design exists in `PLAN.md` (Phase E) but not built.
- Heading-aware rendering (style names are captured but not threaded
  through to `<h1>`-`<h6>` output).
- Native Word tracked-changes handling — identified as redline's single
  biggest competitive gap versus commercial legal redlining tools
  (Litera/Workshare Compare, Draftable); flagged in `PLAN.md` as "not
  scheduled."
- Explicit "moved from/to" labeling (moves currently render as
  delete+insert) — designed in `PLAN.md` (Phase C) but not built.
- Background-corrected (document-frequency-weighted) similarity scoring —
  the containment-aware Jaccard/overlap blend shipped this session is the
  documented "practical default," not that fancier scorer.

## 3. Prototypes & Examples

No standalone prototypes — `docs/workflows.md` has five worked examples
covering plain-text, `.docx`, `.odt`, Phase-0-only inspection, and CLI usage
end to end. See that file for copy-paste-ready code.

A throwaway benchmark script (`bench1.py`/`bench2.py`, built and run in a
scratch `/tmp` copy of the package, not committed to the repo) produced
the performance data cited in `PLAN.md` — worth rebuilding once the DP
performance fix (Phase D) is implemented, to confirm the fix actually
closes the gap.

## 4. Architecture & Key Files

```
redline/
├── __init__.py     # exports compare_text/compare_docx/compare_odt, __version__
├── text.py         # normalization (whitespace/case) + paragraph/sentence/word splitting
├── hashing.py       # 64-bit BLAKE2b for Phase 0's exact-match lookup
├── blocks.py        # Phase 0: transform-ladder block matching + LIS conflict resolution
├── similarity.py    # similarity_score(): Jaccard/overlap-coefficient blend (Phase 1 candidate pairing only)
├── align.py         # Phase 1: recursive paragraph -> sentence -> word matcher
├── ingest.py        # Paragraph extraction: from_text, from_docx, from_odt
├── render.py        # Renders Block/Identity/Edit/Insert/Delete to standalone HTML
├── pipeline.py       # Orchestration: compare_text/compare_docx/compare_odt
├── cli.py           # argparse CLI glue over pipeline.py (no comparison logic itself)
└── __main__.py       # enables `python -m redline`

tests/
├── test_text.py, test_blocks.py, test_align.py, test_similarity.py, test_pipeline.py
├── test_ingest_odt.py   # .odt extraction + compare_odt, pytest.importorskip("odf")
├── test_cli.py           # CLI argument parsing, format auto-detect, exit codes
└── test_render.py        # word-level replace rendering, character-level diffing

docs/{README,CHEATSHEET,API,workflows}.md, TEST_GUIDE.md, PLAN.md,
MANIFEST.txt, verify_install.py, generate_manifest.py, pyproject.toml
```

Data flow: Phase 0 (`blocks.find_blocks`) hashes paragraphs under an
exact -> whitespace -> case transform ladder, resolving duplicate-match
conflicts via longest-increasing-subsequence (`_resolve_order`) — matches
that would "cross" an already-kept match are dropped rather than forced.
**Those dropped matches are exactly the moved-paragraph set** (content
identical under some rung, but out of relative order) — currently
discarded into `unmatched`, this is the basis of the not-yet-built move
detection feature (`PLAN.md` Phase C). The ordered kept blocks form an
"anchor spine" — `pipeline._stitch` walks it, filling each gap between
blocks via Phase 1 (`align.align_paragraphs`), which recurses paragraph ->
sentence -> word using `difflib` ratio thresholds staged behind cheap
upper bounds, falling back to a small alignment DP
(`_align_sequence`/`_dp_scores`, O(n·m)) scored by
`similarity.similarity_score` when recursing. As of this session,
`_align_sequence` skips the DP entirely for the 1-vs-1 case (the only
candidate on each side always pairs, regardless of score). **The DP
remains the confirmed bottleneck** for heavily-revised or
near-duplicate-heavy documents — see `PLAN.md` Phase D for the planned
fix (not yet implemented). `render.py::_render_edit` turns the resulting
`Block`/`Identity`/`Edit`/`Insert`/`Delete` list into one self-contained
HTML file by walking it directly, string-by-string — no intermediate
representation exists yet (see `PLAN.md` Phase B for the proposed semantic
IR). Word-level replace spans get a character-level diff refinement
(`_render_replace`/`_render_token_pair`/`_char_diff_html`,
`WORD_CHAR_THRESHOLD = 0.5`) for both same-token-count pairs and, as of
this session, different-token-count spans (diffed as one joined string
before falling back to a whole-span swap).

`pyproject.toml` registers `redline = "redline.cli:main"` as a console
script; `[project.optional-dependencies]` has `docx` and `odt` extras.

## 5. Recent Decisions & Rationale

- **2026-07-08** — Fixed a second, related over-marking bug Ken caught
  right after the pass above shipped: `_render_replace`'s new
  different-token-count branch still fell back to a whole-span swap when
  a short old token (e.g. `'incorrect.'`) was followed by a much longer
  new phrase that still opened with the same word (e.g. `'incorrect as
  applied to the homomorphic encryption scheme.'`) — re-marking the
  shared word as changed. Root cause: `SequenceMatcher.ratio()` on the
  joined spans is a *character-level* ratio, which (like plain Jaccard)
  penalizes size disparity even under perfect containment — the exact
  same class of bug just fixed in `similarity.py`, showing up one layer
  down. Fix: `render.py` gains `_shorter_side_is_contained(a_tokens,
  b_tokens)`, which checks whether every word in the shorter token list —
  modulo leading/trailing punctuation — appears in the longer one, and
  ORs this into `_render_replace`'s existing `WORD_CHAR_THRESHOLD` gate.
  A raw character-level containment check was tried first and rejected:
  it also fires on coincidental prefixes of unrelated words (`'cat'` is a
  character prefix of `'category'`, verified empirically to score 1.0
  "containment" despite being different words) — comparing whole,
  punctuation-stripped words avoids that false positive while still
  catching the real bug. Added 4 tests to `tests/test_render.py`
  (61 tests total now); `docs/API.md` updated; `MANIFEST.txt` regenerated
  (bundle `76ed3ca0edb7fe66d6ece6e4`).
  - The file-truncation anomaly (Open Question 1 below) recurred twice
    more during this fix, both times on `render.py` and once on
    `tests/test_render.py`. This time it was diagnosed more precisely: the
    `Read` tool (host-side view) showed complete, correct content the
    whole time — only *bash's* view was stale/truncated. So this is a
    one-directional bash-side cache-staleness issue, not actual data loss
    on disk. The heredoc-rewrite workaround still applies whenever bash's
    view needs to be correct too (e.g. before running pytest), but it's
    worth knowing the underlying file was never actually damaged.
- **2026-07-08** — Implemented the three fully-specified, low-risk items
  from `PLAN.md` (Ken: "Implement, modify docs and add new tests as
  needed, all in accordance with Ken's code-quality"). Deliberately
  **excluded** Phase B (semantic IR), Phase C (move detection), and Phase E
  (tables) from this pass — those are large, dependency-ordered
  undertakings that warrant their own dedicated sessions, not a bundled
  add-on to this one. What shipped:
  - **Different-token-count character-diff generalization**
    (`render.py`). `_render_replace`'s mismatched-token-count branch now
    attempts a character-level diff on the joined spans (same
    `WORD_CHAR_THRESHOLD = 0.5` gate) before falling back to a whole-span
    swap. The shared opcode-walk was factored into `_char_diff_html(a, b,
    sm)`, used by both `_render_token_pair` and `_render_replace`.
    Verified against the motivating case: `'This statement is
    incorrect.'` -> `'...now clearly incorrect"'` now marks only the two
    inserted words and the punctuation change, leaving `incorrect`
    untouched.
  - **1-vs-1 forced-pairing fix** (`align.py::_align_sequence`). A hole
    with exactly one unit on each side now pairs unconditionally, instead
    of being gated through `PAIR_THRESHOLD` (0.15) like any other
    candidate pair. Fixes a genuine bug: two totally dissimilar sole
    occupants of a hole used to render as a disconnected `Delete`+`Insert`
    instead of one `Edit`, even though being each other's only candidate
    is by itself sufficient justification to pair. A 1-vs-M hole is
    unaffected — it still goes through the DP and `PAIR_THRESHOLD` as
    before.
  - **Containment-aware similarity score** (`similarity.py`). Renamed
    `jaccard()` to `similarity_score()` (honest naming — it's no longer
    plain Jaccard) and changed its behavior: below
    `PAIR_OVERLAP_THRESHOLD` (default 0.5, measured as the overlap
    coefficient `|A∩B|/min(|A|,|B|)`), the score is unchanged plain
    Jaccard; above it, the score ramps linearly from Jaccard up to 1.0 as
    overlap approaches 1.0. Fixes plain Jaccard's systematic
    under-scoring of genuine containment (a short unit fully absorbed
    into a longer edited one used to score ~0.19, barely above
    `PAIR_THRESHOLD`) without inflating scores for short, unrelated text
    that coincidentally shares words (verified: an unrelated control case
    stays at plain Jaccard, ~0.13). All call sites in `align.py`
    (`_dp_scores`, `_traceback`) updated to the new name.
  - Added `tests/test_similarity.py` (8 tests: edge cases, threshold
    boundary, containment case, false-positive control). Extended
    `tests/test_render.py` (+1 test: different-count-clears-threshold
    case) and `tests/test_align.py` (+3 tests: 1-vs-1 forced pairing at
    both the `_align_sequence` and end-to-end level, plus a 1-vs-M
    control confirming the fast path doesn't over-fire).
  - `docs/API.md`, `docs/CHEATSHEET.md`, `TEST_GUIDE.md` updated for the
    rename and new behavior. `MANIFEST.txt` regenerated (bundle
    `a10d64e3b307b8cfcdf540d4`, 57 tests, all passing, `verify_install.py`
    clean).
  - **`PLAN.md`'s decisions ledger updated**: these three items moved from
    "designed, not yet in code" / roadmap phases into "shipped."
  - Encountered the same file-truncation anomaly from the prior session's
    incident (see below) on `similarity.py`, `align.py`, `render.py`, and
    `generate_manifest.py` mid-edit — each time the `Edit`/`Write` tool
    reported success but bash's view showed the file truncated mid-token
    at a consistent byte count. Fixed each occurrence the same way:
    rewrite directly via a bash heredoc, then verify with `ast.parse`.
    Not yet root-caused; see Open Questions.
- **2026-07-08** — Architecture review (independent Opus consult, second
  one that session): recommended **against** unifying Phase 0/Phase 1
  into one recursive `SequenceMatcher`-based engine (Ken's "difflib works
  in any alphabet" proposal). Verdict: elegant but doesn't solve the
  actual problem — `SequenceMatcher` matches by strict equality only, so
  on the two workloads that are actually slow (heavily-revised documents,
  near-duplicate boilerplate) it would find zero matching blocks and
  still need the same O(n·m) fuzzy-pairing DP underneath; the cost just
  relocates, it doesn't disappear. Full reasoning and the semantic-IR
  counter-proposal are in `PLAN.md`.
- **2026-07-08** — Ran real (not theoretical) benchmarks on a scratch copy
  of the package: light-edit documents (5% of paragraphs touched) scale
  linearly — 50,000 paragraphs, 2.3s, 115MB peak. Heavily-revised
  documents (~100% of paragraphs touched) and near-duplicate-heavy
  documents scale super-linearly — 8,000 fully-changed paragraphs took
  27s. Root cause and planned fix are in `PLAN.md` Phase D.
- **2026-07-08** — Move-detection design proposed (Ken's idea), table
  row-diffing approach reflected on (Ken's request, explicitly not
  implemented that session), and a semantic IR node model adopted as the
  target output structure for both. Full designs, caveats, and scope
  boundaries are in `PLAN.md` (Phases B, C, E) rather than duplicated
  here.
- **2026-07-08** — Root-caused (partially) a multi-hour file-access
  incident on `TEST_GUIDE.md`/`KT.md`: both became inaccessible to bash
  *and* the host file tool simultaneously. Ruled out an external lock via
  `lsof`/`strace`; resolved by direct deletion + recreation. *(inferred: a
  FUSE-bridge cache-coherency bug specific to that session; root cause not
  fully confirmed — and, per this session's recurrence above, apparently
  not session-specific after all.)*
- **2026-07-08** — Shipped the original punctuation-diff fix: word-level
  "replace" opcodes with *equal* token counts on both sides get a nested
  character-level diff (`render.py`'s `_render_replace`/
  `_render_token_pair`, `WORD_CHAR_THRESHOLD = 0.5`) instead of a
  whole-word swap. Fixes the reported bug where trailing-punctuation-only
  changes (e.g. `technology".` vs `technology"`) marked the entire word
  as changed.

## 6. Open Questions & Blockers

1. **A file-truncation/staleness anomaly has now occurred across two
   separate sessions**, affecting different files each time
   (`TEST_GUIDE.md`/`KT.md` previously; `similarity.py`/`align.py`/
   `render.py`/`generate_manifest.py`/`tests/test_render.py`/
   `docs/API.md` this session — the last two recurring even after the
   session's earlier occurrences). Refined understanding this session: in
   every case checked directly, the `Read` tool (host-side file view)
   showed complete, correct content; only *bash's* view (`cat`/`wc`/
   `python3` imports) was stale or truncated. So this looks like a
   one-directional bash-side read-cache staleness bug, not actual data
   loss on disk — but it's serious for anything that runs via bash
   (`pytest`, `python3 generate_manifest.py`), since a stale bash read
   there really does execute against wrong content. Workaround (rewrite
   directly via a bash heredoc, then verify with `ast.parse` from bash)
   has worked every time. Still unconfirmed why it happens or how to
   avoid triggering it. Worth escalating if it starts affecting things
   the workaround can't easily catch (e.g. binary files, or if `ast.parse`
   ever passes on stale-but-syntactically-valid truncated content).
2. **Semantic IR / XML output, move detection, table diffing (`PLAN.md`
   Phases B, C, E): fully designed, not yet implemented.** Sequencing
   dependency: B should land before C/E since both need nesting a flat
   list can't represent. Ken has not yet asked to start any of these.
3. **Real performance fix for the O(n·m) alignment DP (`PLAN.md` Phase
   D)**: sentence-level exact-match pre-pass plus the shape-based fast
   paths (1-vs-1 done this session; 1-vs-M/N-vs-1/N-vs-M remain on the
   DP). Not yet scoped as its own implementation pass.
4. **Paragraph-level `SequenceMatcher` unification: parked, not rejected
   outright** — see `PLAN.md` "Explicitly rejected." Worth revisiting only
   if a real (not theoretical) duplicate-boilerplate misassignment bug
   shows up in practice.
5. **`.odt` ingestion code's original authorship is still unconfirmed**
   (functionally fine and explicitly wanted). Low priority, informational
   only. Carried over from a prior session.
6. **No git commits made yet.** Repo is initialized; no commit has been
   made because Ken hasn't asked for one yet.

## 7. Next Steps

1. Ken decides whether/when to start `PLAN.md`'s remaining phases: (B)
   semantic IR foundation, (C) move detection, (D) the O(n·m) DP
   performance fix, (E) table diffing. None block each other except B vs
   C/E.
2. Make an initial git commit — repo exists, nothing committed yet.
3. Consider a dedicated `.docx` ingestion test file (`test_ingest_odt.py`
   exists; no `test_ingest_docx.py` equivalent yet).
4. If the file-truncation anomaly (Open Question 1) recurs again, escalate
   rather than continuing to route around it silently.

## 8. Last Updated

2026-07-08T22:48:03Z | Trigger: manual | Staleness: **Fresh**.
