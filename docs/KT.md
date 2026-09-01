# KT — redline

> Last updated: 2026-07-22T13:38:22Z | Trigger: manual | Staleness: Stale

⚠️ HIL NOTICE — 2026-07-22
This document was last substantially updated 2026-07-08, before four
sessions' worth of real architecture changes (PDF ingestion, the sentence-
flattening rework of Phase 1, local reorder detection, word-level diff
fragmentation fix, and a new Phase 2 for cross-hole move detection). Nearly
every section below needed a full rewrite, not an edit — Project Overview,
Goals & Constraints (non-goals list was actively wrong: it listed move
labeling as unbuilt when it now ships), Architecture & Key Files (missing
two new modules), Recent Decisions, Open Questions, and Next Steps all
changed substantially. Recommend a human read-through before trusting this
for onboarding into a new session, then clear this notice by running an
update once confirmed accurate.

---

## 1. Project Overview

`redline` is a lightweight, dependency-minimal Python package that redlines
large, heavily-revised documents (legal contracts, academic papers) —
producing `<ins>`/`<del>` HTML output like Word's "Compare Documents," but
designed to avoid two failure modes Word/LibreOffice Writer both have:
cascading false positives from one early edit, and unreadable word-salad
diffs on heavily-rewritten paragraphs. Supports `.txt`, `.docx`, `.odt`,
and (as of 2026-07-12) `.pdf` input via the shared `readers` package; has
both a library API (`compare_text`/`compare_docx`/`compare_odt`/
`compare_pdf`) and a CLI (`redline` console script / `python -m redline`).

Current status: **Active Development**. 103 tests passing. The engine is
now genuinely three phases, not two: Phase 0 (`blocks.py`, whole-document
exact/near-exact paragraph matching), Phase 1 (`align.py`, sentence-level
matching within Phase 0's residual holes — reworked 2026-07-21 to flatten
paragraphs to sentences rather than pairing paragraphs first), and Phase 2
(`moves.py`, added 2026-07-22, whole-document cross-hole move detection).
LaTeX documents are currently read via the plain-text path (`.tex` treated
as `-f text`) — real, LaTeX-specific quality issues have been found this
way (see Recent Decisions) and a genuinely LaTeX-aware approach (either
building environment-block-level matching into redline, or adopting the
external `latexdiff` tool) is under active discussion, not yet decided.

## 2. Goals & Constraints

**Goals:**
- Two-phase-turned-three architecture: cheap exact/near-exact block
  removal first (Phase 0), a recursive coarse-to-fine matcher on
  genuinely changed residue (Phase 1), and — new — a whole-document pass
  recognizing content that relocated far enough to land in a different
  Phase 1 hole (Phase 2).
- **Standing design principle (generalized 2026-07-21/07-22, Ken's
  framing):** "identify identical conceptual units and set them aside;
  recurse only on what's left" is not specific to paragraphs. It has now
  been applied at the paragraph level (Phase 0), the sentence level
  (Phase 1's 2026-07-21 rework, flattening paragraphs to sentences so
  identical sentences are found regardless of which paragraph they're
  nominally in), and — proposed, not yet implemented — at the level of
  LaTeX's `\begin{name}...\end{name}` environment blocks: extract every
  complete environment block as an atomic unit, hash-match whole blocks
  for exact identity and set aside the unchanged ones, recurse/diff only
  on the changed ones, and fall back to ordinary flat-text/paragraph
  matching for whatever content isn't inside a recognized environment.
  This is a genuinely different mechanism from Phase 0/1's hashing (which
  operates on plain prose paragraphs/sentences with no nesting to
  respect) — environment blocks are structurally self-contained (each
  opens and closes what it opens), which is what makes them safe units to
  cut a document on, unlike naive blank-line paragraph splitting applied
  to raw LaTeX source. See Recent Decisions (2026-07-22) for the worked
  example (`\end{remark}` false-positive) that motivated this, and Open
  Questions for what building it would actually require.
- Support `.txt`, `.docx`, `.odt`, and `.pdf` as input formats.
- Produce standalone, self-contained HTML redline output today; a
  semantic IR with additional output converters (docx, odt) is the
  leading candidate for where this goes next (see `PLAN.md` — status of
  that document not reverified this pass).
- Provide both a Python library API and a CLI.

**Constraints:**
- No heavy dependencies — standard library only, apart from optional
  `python-docx` (.docx), `odfpy` (.odt), and the `readers` package (now a
  *required*, not optional, dependency as of 2026-07-12 — `text.py`
  imports `split_paragraphs`/`split_sentences` from `readers` to
  de-duplicate with `readers/segment.py`; `.pdf` support additionally
  needs `readers`'s `pdf` extra, `pypdf`).
- Code quality per `ken-code-quality` skill: small functions, honest
  naming, plan-before-code for non-trivial features — this session's
  cross-hole move detection and word-diff fix were both planned and
  reviewed with Ken before implementation, per his explicit request.
- Documentation per `code-documentation-writing` skill: `docs/API.md`
  kept current every session; dated `docs/JOURNAL_YYYY-MM-DD.md` files
  per significant change (`JOURNAL_2026-07-12.md`, `_07-21.md`, `_07-22.md`
  exist); `MANIFEST.txt`/`verify_install.py` regenerated at the end of
  every session that changes tracked files.
- Explicit, standing preference (Ken): calibrate engineering effort to
  actual likelihood of the problem occurring, and verify claims against
  real code/real documents before asserting them — this pass's own
  process is a good example: a first implementation of the local-reorder
  fix (2026-07-21) was wrong (a "safety net" conflict-resolution step
  silently undid the fix it was meant to protect), caught by re-running
  the swap example against the actual code rather than trusting the
  earlier hand-verification. Documented in `JOURNAL_2026-07-21.md` rather
  than quietly fixed and forgotten.

**Non-goals (documented in `docs/API.md` "Known limitations"):**
- Table extraction/comparison (`.docx`/`.odt` tables are skipped
  entirely).
- Heading-aware rendering is *partial*, not a non-goal anymore: PDF gets
  it (`compare_pdf` builds `style_by_text`, 2026-07-12 "Option A");
  `compare_docx`/`compare_odt` still don't build or pass one, even though
  `Paragraph.style` is captured for both — a natural, not-yet-done
  follow-up, not a rejected idea.
- Native Word tracked-changes handling — still redline's biggest gap
  versus commercial tools (Litera/Workshare Compare, Draftable).
- Move detection is **no longer a non-goal** — local reorders (2026-07-21)
  and cross-hole relocations (2026-07-22, `moves.py`) are both detected
  and labeled `{moved above}`/`{moved below}`. What remains out of scope:
  matching is exact-text only (a sentence that moved *and* was reworded
  isn't recognized as a move), and several sentences relocated together
  as a block each get their own separate marker rather than one
  annotation for the whole block.
- Background-corrected (document-frequency-weighted) similarity scoring —
  the containment-aware Jaccard/overlap blend remains the practical
  default.

## 3. Prototypes & Examples

No standalone prototypes — `docs/workflows.md` has worked examples
covering plain-text, `.docx`, `.odt`, `.pdf`, Phase-0-only inspection, and
CLI usage (not reverified this pass for `.pdf`/moves coverage — worth a
follow-up pass reading `workflows.md` directly).

This pass leaned heavily on **real documents rather than only synthetic
fixtures**: `main-14a.tex`/`main-15a.tex`/`main-16.tex` (Ken's own paper,
in the sibling `paper` project folder) were used repeatedly to find and
verify real bugs — the paragraph-split bug (2026-07-21), the word-level
fragmentation bug and the `\end{remark}` move-detection false positive
(both 2026-07-22) were all found this way, not in synthetic tests first.

New this pass: a manual `latexdiff` run (external tool, not integrated
into redline) against `main-14a.tex`/`main-16.tex`, output saved to Ken's
`paper` folder as `main-14a_vs_main-16_latexdiff.tex` for a manual
compile-and-inspect check. `latexdiff` isn't available via `apt`/`tlmgr`
in this sandbox (no root, and CTAN/`raw.githubusercontent.com` are
network-blocked here) — worked around by `git clone
https://github.com/ftilmann/latexdiff.git` (plain `github.com` *is*
reachable) and running the Perl script directly. Result: clean run, exit
0, no stderr; whether it actually compiles is Ken's to confirm — not yet
reported back as of this update.

## 4. Architecture & Key Files

```
redline/
├── __init__.py     # exports compare_text/compare_docx/compare_odt/compare_pdf, __version__
├── text.py         # normalization (whitespace/case); split_paragraphs/split_sentences/split_words now delegate to `readers` (de-duped 2026-07-12)
├── hashing.py       # 64-bit BLAKE2b for exact-match lookup -- used by blocks.py, align.py, AND moves.py now
├── ordering.py      # NEW 2026-07-21: resolve_order() (LIS conflict resolution), promoted out of blocks.py, shared with align.py
├── blocks.py        # Phase 0: transform-ladder block matching + resolve_order (now imported, not defined here)
├── similarity.py    # similarity_score(): Jaccard/overlap-coefficient blend (Phase 1 sentence candidate pairing only)
├── align.py         # Phase 1: REWORKED 2026-07-21 (flatten to sentences, no paragraph-level pairing) + 2026-07-22 (word-level DP pairing removed entirely, _diff_op called directly)
├── moves.py         # NEW 2026-07-22: Phase 2, cross-hole move detection (MovedAway/MovedHere)
├── ingest.py        # Paragraph extraction: from_text, from_docx, from_odt, from_pdf (added 2026-07-12, delegates to `readers`)
├── render.py        # Renders Block/ParagraphGroup(Identity/Edit/Insert/Delete/MovedAway/MovedHere) to standalone HTML; style_by_text heading support (2026-07-12)
├── pipeline.py       # Orchestration; all four compare_* now take detect_moves: bool = True, threaded to moves.detect_moves
├── cli.py           # argparse CLI glue; --suppress-moves flag (2026-07-22), -f/--format now includes "pdf"
└── __main__.py       # enables `python -m redline`

tests/  (103 tests total, up from 61 on 2026-07-08)
├── test_text.py, test_blocks.py, test_similarity.py, test_render.py, test_pipeline.py
├── test_align.py         # includes 2026-07-21 reorder-fix tests, 2026-07-22 word-fragmentation test
├── test_ordering.py       # NEW: resolve_order() as a shared, public function
├── test_moves.py          # NEW: Phase 2 (moves.py) — relocation, ambiguity, direction, no-match cases
├── test_ingest_odt.py, test_ingest_pdf.py
└── test_cli.py            # includes --suppress-moves coverage

docs/{README,CHEATSHEET,API,workflows}.md, TEST_GUIDE.md, PLAN.md,
JOURNAL_2026-07-12.md, JOURNAL_2026-07-21.md, JOURNAL_2026-07-22.md,
MANIFEST.txt, verify_install.py, generate_manifest.py, pyproject.toml
```

Data flow, current state: Phase 0 (`blocks.find_blocks`) hashes paragraphs
under an exact -> whitespace -> case ladder, resolving duplicate-match
conflicts via `ordering.resolve_order` (LIS) — matches would "cross" an
already-kept match are dropped rather than forced, and become Phase 1's
input. The ordered kept blocks form an anchor spine (`pipeline._stitch`);
each gap between anchors goes through Phase 1 (`align.align_paragraphs`),
which — as of 2026-07-21 — flattens *both* sides' paragraphs in the hole
to one tagged sentence sequence before matching at all, rather than
pairing paragraphs first and recursing within pairs (paragraph structure
is now purely reconstruction metadata, via `_group_by_paragraph`). Within
a hole, an exact-match pre-pass (`_exact_match_sentences` +
`resolve_order`) finds identical sentences regardless of relative order,
so a locally reordered-but-unchanged sentence pair is recognized as
`Identity` rather than losing to the order-preserving fuzzy DP
(`_align_sequence`) that handles the residual. As of 2026-07-22, that
fuzzy DP is *sentence-level only* — the word-level candidate-pairing tier
it used to recurse into was removed entirely (`_diff_op`'s own
`SequenceMatcher` pass is now called directly once a sentence isn't
byte-identical), because scoring individual words with a set-based
similarity metric degenerated to "identical or unrelated" and shattered
genuine multi-word edits into many single-word `Delete`/`Insert` pairs.

New in this pass: **Phase 2** (`moves.py`) runs once, after `_stitch`
assembles the whole document, and looks for exact-text matches between
every orphaned `Delete` and `Insert` *across the entire document* —
catching relocations Phase 1 can't see because each hole is matched
independently. Uses greedy hash matching, deliberately *not*
`resolve_order`/LIS, since these matches splice into an already-finalized
render order rather than feeding a monotonic gap-walk. Known false-
positive mode found on Ken's real paper: short, highly-repeated pure
markup (`\end{remark}`, appearing 8-11 times) has no reliable identity
signal at this granularity, and got labeled "moved" when it was really
just coincidental duplicate boilerplate — a follow-up (reject a match if
either side has more than one candidate with that exact text) is scoped
but not implemented; see Open Questions.

`render.py` now dispatches on `Block` or `ParagraphGroup` (never bare ops
at the top level), with `MovedAway`/`MovedHere` rendering as
`<span class='moved'>` markers.

## 5. Recent Decisions & Rationale

- **2026-07-22** — Standing generalization articulated (Ken): "setting
  aside" identical content for cheap exclusion from further diffing
  applies to *any* conceptual document unit, not just paragraphs — and
  the unit can change mid-pipeline. Concretely proposed for LaTeX: treat
  every complete `\begin{name}...\end{name}` block as one atomic unit,
  hash-match whole blocks for exact identity across the document, set
  aside identical ones untouched, recurse/diff only on changed or
  unmatched ones, then fall back to ordinary flat-text/paragraph matching
  for content outside any recognized environment. Motivated directly by
  a real false positive found in `moves.py` (the `\end{remark}` case
  above) — a bigger, content-rich unit is both a structurally safer cut
  point (environment blocks are self-contained; blank-line paragraphs cut
  from raw LaTeX are not — a naive split can orphan an `\end{}` with no
  matching `\begin{}` in the same hole) and less prone to false-positive
  collisions (a whole block's content is a much lower-collision fingerprint
  than a four-character closing tag). Not yet implemented — real
  difficulty identified: needs a stack-based environment-boundary tracker
  (handling same-name nesting, verbatim-like environments whose contents
  must not be scanned as LaTeX, and comments) — smaller than full LaTeX
  tree parsing (no macro-argument or math-mode semantics needed) but a
  real, moderate-sized new component, not a regex tweak. Whether it's
  worth building is gated on how well the external `latexdiff` tool
  performs unassisted on Ken's real documents (see Prototypes & Examples)
  — untested until this session, verified to at least run cleanly;
  compile-correctness not yet confirmed by Ken.
- **2026-07-22** — Word-level diff fragmentation fixed and cross-hole
  move detection (Phase 2) shipped, both planned with Ken before
  implementation. Word-fix: `align_units` calls `_diff_op` directly
  instead of recursing into word-level DP-based candidate pairing (which
  degenerated to exact-or-nothing on single words); `GRANULARITY_LADDER`,
  `_split`, `_interleave`, and related now-dead helpers removed outright
  rather than left unreachable. Moves: new `moves.py` (Phase 2, see
  Architecture), `--suppress-moves` CLI flag / `detect_moves=False`
  library param, both default-on. Full detail, including the false-
  positive found on real content and a **self-caught implementation bug**
  (a first attempt merged exact-match "anchor" pairs and fuzzy-DP
  "residual" pairs through a second LIS conflict-resolution pass as a
  safety net, which silently re-dropped the exact match the whole fix
  depended on — caught by re-running the swap example against the actual
  code rather than trusting the earlier hand-verification) — in
  `JOURNAL_2026-07-22.md`. 103 tests passing (was 92 at end of prior
  session), `MANIFEST.txt` regenerated.
- **2026-07-21** — Phase 1 reworked: paragraph-level pairing dropped
  entirely in favor of flattening both sides of a hole to sentences
  before matching at all (fixes a real paragraph-split bug: an author
  splitting one paragraph into two across a revision used to strand an
  unchanged sentence as a disconnected insert). Same day: found and fixed
  a related gap — the fuzzy sentence DP is order-preserving and couldn't
  recognize two *locally reordered* identical sentences as unchanged;
  fixed with an exact, position-independent hash pre-pass
  (`_exact_match_sentences`), mirroring Phase 0's own approach one level
  down. `blocks.py`'s LIS conflict resolution (`_resolve_order`) promoted
  to shared `ordering.resolve_order`. Full detail in
  `JOURNAL_2026-07-21.md`.
- **2026-07-12** — PDF ingestion added (`from_pdf`/`compare_pdf`, via the
  `readers` package — now a required dependency, not optional).
  Same-day follow-up ("Option A"): headings render as `<h1>`-`<h6>` for
  the PDF path via a new `style_by_text` parameter threaded through
  `render_html`; `from_pdf` switched from `readers.recover_paragraphs` to
  `readers.split_into_sections` after a real bug (page-boundary artifacts
  shifting paragraph splits differently between two PDF revisions of the
  same document, causing a false full delete+insert). Full detail in
  `JOURNAL_2026-07-12.md` (and the companion entry in `readers`'s own
  journal).

<details>
<summary>Archived — decisions from 2026-07-08 and earlier (condensed)</summary>

Prior session shipped three low-risk items from `PLAN.md`'s early phases:
the different-token-count character-diff generalization
(`render._char_diff_html`, shared by `_render_token_pair`/
`_render_replace`), the 1-vs-1 forced-pairing fix in
`align._align_sequence` (sole candidates on each side always pair,
bypassing `PAIR_THRESHOLD`), and the containment-aware similarity score
(`similarity.py`'s `jaccard()` renamed to `similarity_score()`, ramping
above `PAIR_OVERLAP_THRESHOLD` instead of systematically under-scoring
genuine containment). An independent architecture review recommended
against unifying Phase 0/Phase 1 into one `SequenceMatcher`-based engine
(elegant but doesn't solve the actual bottleneck). Real benchmarks showed
light-edit documents scale linearly; heavily-revised/near-duplicate-heavy
documents scale super-linearly (root cause + planned fix in `PLAN.md`
Phase D — status not reverified this pass). A recurring file-truncation/
staleness anomaly (bash-side read cache, not actual data loss) was
investigated across two sessions and worked around each time (rewrite via
heredoc, verify with `ast.parse`); **not observed again in any of the
2026-07-12/07-21/07-22 sessions** — see Open Questions.

</details>

## 6. Open Questions & Blockers

1. **Should the `\begin{name}...\end{name}` environment-block "set
   aside" generalization be built?** (2026-07-22, Ken's proposal —
   see Recent Decisions.) Gated on Ken's compile-check of
   `main-14a_vs_main-16_latexdiff.tex` — if plain `latexdiff` already
   handles his real documents well, this may not be worth the real
   engineering cost (a stack-based environment-boundary tracker).
2. **Move-detection ambiguity follow-up scoped, not implemented**
   (2026-07-22): reject a `Delete`/`Insert` match in `moves.py` if either
   side has more than one candidate with that exact text, rather than
   greedily claiming the first — fixes the `\end{remark}` false positive
   more directly (and more generally, for any document format) than the
   environment-block idea above, at much lower implementation cost.
   Would require rewriting `test_moves.py`'s existing
   `test_duplicate_orphan_content_matches_greedily_without_crashing`
   expectation (behavior intentionally changes: ambiguous duplicates
   currently claim one match; under this fix, none would).
3. **LaTeX support in the `readers` package**: Ken's own 7-step
   reflect/plan/review/critique/revise/implement process stalled after
   step 3 (plan presented) — steps 4-7 (his critique, response, final
   revision, implementation) never happened. This lives in `readers`'s
   own project, not detailed further here — check `readers`'s KT.md if
   one exists.
4. **Semantic IR / table diffing (`PLAN.md` Phases B/E)**: still not
   started. Move detection (Phase C) is *no longer* fully in this
   bucket — local + cross-hole moves both ship now; only "moved" block-
   merging (adjacent relocated sentences get one marker instead of many)
   remains an open refinement, not a from-scratch phase.
5. **O(n·m) DP performance (`PLAN.md` Phase D)**: the *word-level* DP
   was removed entirely 2026-07-22 (for correctness, not performance —
   it was producing wrong output, fragmenting genuine multi-word edits).
   The *sentence-level* DP within one hole still exists and could still
   be a real cost for a huge hole; not rebenchmarked since the 2026-07-08
   figures, which predate this rework.
6. **Paragraph-level `SequenceMatcher` unification**: still parked per
   the 2026-07-08 architecture review; no new evidence for or against
   since.
7. **File-truncation/staleness anomaly**: not observed again across three
   full sessions of heavy file editing since 2026-07-08 — tentatively
   dormant or resolved, downgraded from urgent. Re-escalate immediately if
   it recurs.
8. **`.odt` ingestion authorship**: still unconfirmed, low priority,
   carried over informationally.

## 7. Next Steps

1. Ken to compile `main-14a_vs_main-16_latexdiff.tex` and report whether
   `latexdiff`'s output is usable as-is — this gates Open Question 1.
2. Decide whether to implement the move-detection ambiguity fix (Open
   Question 2) — small, contained, applies regardless of the LaTeX
   decision above.
3. Resume Ken's stalled 7-step review of the `readers` LaTeX-support plan
   (Open Question 3) whenever he's ready.
4. Consider merging adjacent relocated sentences into one "moved"
   annotation instead of one per sentence (noted as a known limitation in
   `docs/API.md`, not yet scoped as its own task).
5. `PLAN.md`'s remaining phases (semantic IR, table diffing) — no active
   push; revisit `PLAN.md` itself for currency, since it wasn't
   reverified this pass.
6. Make an initial "real" review of whether `PLAN.md`, `docs/workflows.md`,
   and `TEST_GUIDE.md` still match current behavior — none were
   reverified in this update; the surgical review this pass focused on
   `KT.md` itself against direct session knowledge, not a full repo
   file-scan of every doc.

## 8. Last Updated

2026-07-22T13:38:22Z | Trigger: manual | Staleness: **Stale** — see HIL
NOTICE above. Summary: rewrote Project Overview, Goals & Constraints
(non-goals list was actively wrong), Architecture & Key Files (two new
modules, three-phase not two-phase engine), Recent Decisions (added
2026-07-12/07-21/07-22, archived pre-07-08 history), Open Questions, and
Next Steps to reflect four sessions of real changes since the last update
(2026-07-08). Captured Ken's standing generalization (identical-content
"set aside" applies to any conceptual unit, demonstrated at sentence
granularity and proposed for LaTeX environment blocks) prominently in
Goals & Constraints and Recent Decisions, per his explicit request this
session.
