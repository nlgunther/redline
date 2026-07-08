# KT — redline

> Last updated: 2026-07-08T13:26:00Z | Trigger: manual | Staleness: Fresh

---

## 1. Project Overview

`redline` is a lightweight, dependency-minimal Python package that redlines
large, heavily-revised documents (legal contracts especially) — producing
`<ins>`/`<del>` HTML output like Word's "Compare Documents," but designed to
avoid two failure modes Word/LibreOffice Writer both have: cascading false
positives from one early edit, and unreadable word-salad diffs on
heavily-rewritten paragraphs. Supports `.txt`, `.docx`, and `.odt` input,
and now has both a library API and a command-line interface.

Current status: **Active Development** (core library, all three input
formats, and the CLI are implemented and tested; version control setup is
still in progress).

## 2. Goals & Constraints

**Goals:**
- Two-phase comparison: cheap exact/near-exact block removal first, then a
  recursive coarse-to-fine matcher only on genuinely changed residue.
- Support `.txt`, `.docx`, and `.odt` as input formats.
- Produce standalone, self-contained HTML redline output.
- Provide both a Python library API (`compare_text`/`compare_docx`/`compare_odt`)
  and a CLI (`redline` console script / `python -m redline`).

**Constraints:**
- No heavy dependencies — standard library only, apart from optional
  `python-docx` (.docx) and `odfpy` (.odt), each imported lazily inside its
  own ingest function.
- Code quality per `ken-code-quality` skill: small functions (<30 lines
  typical), files <600 lines, plan-before-code for non-trivial features.
- Documentation per `code-documentation-writing` skill: every module needs
  `docs/README.md`, `docs/CHEATSHEET.md`, `docs/API.md`, `docs/workflows.md`
  coverage, plus `TEST_GUIDE.md` for the test suite.

**Non-goals (documented in `docs/API.md` "Known limitations"):**
- Table extraction/comparison (`.docx`/`.odt` tables are skipped entirely).
- Heading-aware rendering (style names are captured but not threaded
  through to `<h1>`-`<h6>` output).
- Native Word tracked-changes handling.
- Explicit "moved from/to" labeling (moves render as delete+insert).
- Background-corrected (document-frequency-weighted) similarity scoring —
  plain Jaccard is used instead.

## 3. Prototypes & Examples

No standalone prototypes — `docs/workflows.md` has five worked examples
covering plain-text, `.docx`, `.odt`, Phase-0-only inspection, and CLI usage
end to end. See that file for copy-paste-ready code.

## 4. Architecture & Key Files

```
redline/
├── __init__.py     # exports compare_text/compare_docx/compare_odt, __version__
├── text.py         # normalization (whitespace/case) + paragraph/sentence/word splitting
├── hashing.py       # 64-bit BLAKE2b for Phase 0's exact-match lookup
├── blocks.py        # Phase 0: transform-ladder block matching + LIS conflict resolution
├── similarity.py    # Jaccard word-overlap scoring (Phase 1 candidate pairing only)
├── align.py         # Phase 1: recursive paragraph -> sentence -> word matcher
├── ingest.py        # Paragraph extraction: from_text, from_docx, from_odt
├── render.py        # Renders Block/Identity/Edit/Insert/Delete to standalone HTML
├── pipeline.py       # Orchestration: compare_text/compare_docx/compare_odt
├── cli.py           # argparse CLI glue over pipeline.py (no comparison logic itself)
└── __main__.py       # enables `python -m redline`

tests/
├── test_text.py, test_blocks.py, test_align.py, test_pipeline.py
├── test_ingest_odt.py   # .odt extraction + compare_odt, pytest.importorskip("odf")
└── test_cli.py           # CLI argument parsing, format auto-detect, exit codes

docs/{README,CHEATSHEET,API,workflows}.md, TEST_GUIDE.md,
MANIFEST.txt, verify_install.py, generate_manifest.py, pyproject.toml
```

Data flow: Phase 0 (`blocks.find_blocks`) hashes paragraphs under an
exact -> whitespace -> case transform ladder, resolving duplicate-match
conflicts via longest-increasing-subsequence. The ordered blocks form an
"anchor spine" — `pipeline._stitch` walks it, filling each gap between
blocks via Phase 1 (`align.align_paragraphs`), which recurses
paragraph -> sentence -> word using `difflib` ratio thresholds staged
behind cheap upper bounds, falling back to a small Jaccard-scored
alignment DP when recursing. `render.render_html` turns the resulting
`Block`/`Identity`/`Edit`/`Insert`/`Delete` list into one self-contained
HTML file. `cli.py` is a thin routing layer on top — no logic of its own.

`pyproject.toml` registers `redline = "redline.cli:main"` as a console
script; `[project.optional-dependencies]` has `docx` and `odt` extras.

## 5. Recent Decisions & Rationale

- **2026-07-08** — Confirmed the bash sandbox mount bug from Open Question #1
  is no longer reproducing: bash can now open, read, and write files in the
  project folder (direct `cat`/`head` matched the `Read` tool's output
  exactly for `pyproject.toml` and `redline/text.py`), and `git status`
  now runs without the earlier "not a git repository" error (repo still
  has zero commits). *(inferred: transient/session-scoped, not a
  project-level issue, consistent with the original inference below.)*
- **2026-07-08** — Found `MANIFEST.txt` is stale: `verify_install.py`
  reports a hash MISMATCH for `redline/text.py` (bundle
  `e6837f143034ac15d9e3f8f0` actual vs. `e4efdd314e60df20f9542189`
  recorded), even though the file's mtime predates `MANIFEST.txt`'s own
  generation timestamp. The `Read` tool and bash agree exactly on the
  file's current content, which rules out the bash/host disagreement bug
  from the entry below — the manifest itself just doesn't match what's on
  disk, for a reason that isn't yet clear. Not regenerated as part of this
  update; needs Ken to confirm no unintended edit landed in `text.py`
  first (see Open Questions).
- **2026-07-07** — Added a CLI (`redline/cli.py`, `redline/__main__.py`,
  console script entry). Chose `argparse` over `click` to preserve the
  project's stdlib-only dependency philosophy. Upfront file-existence
  checks (before either format's reader runs) give a consistent error
  message regardless of format; a single broad `except Exception` in
  `main()` avoids ever printing a raw traceback to an end user.
  `--version` reads the installed package version via
  `importlib.metadata`, falling back to a hardcoded string when run
  from source without installation.
- **2026-07-07** — Fixed `pyproject.toml` (restored the `odt` optional
  dependency and `[tool.pytest.ini_options]`, which a prior session's
  brief flagged as possibly truncated on disk) and regenerated
  `MANIFEST.txt` (bundle `e4efdd314e60df20f9542189`, 38 tests, all
  `verify_install.py` checks pass).
- **2026-07-07** — Diagnosed a persistent environment bug: this session's
  bash sandbox can `stat`/list files in the project's mounted folder but
  cannot `open()` pre-existing ones (readdir/getattr succeed, open fails
  ENOENT). Reconnecting the folder, rewriting files via the host-side
  tools, and `fusermount -u` all failed to fix it. Workaround adopted:
  mirror the package into a scratch directory bash *can* read/write for
  running `pytest`, while all real edits go through the host-side
  Read/Write/Edit tools (confirmed reliable throughout). *(inferred: this
  is a sandbox/session-level issue, not a project-level one)*.
- **2026-07-07** — Ken ran `git init` in the project folder. Git commands
  still fail from this session's bash (`fatal: not a git repository`) —
  confirmed this is the same mount bug above, not a problem with the
  repo itself (`.git/HEAD` reads correctly via the host-side tools).
- *(from a prior session's handoff brief, date uncertain)* — `.odt`
  support (`from_odt`, `compare_odt`) was found already implemented with
  unconfirmed authorship. Ken has since explicitly requested `.odt`
  support in this session, which resolves the "should we keep it"
  question even though the original authorship is still unconfirmed.

## 6. Open Questions & Blockers

1. ~~Bash sandbox cannot reliably read/write the real project folder at
   the filesystem-open level~~ **RESOLVED 2026-07-08** — bash can now
   open/read/write project files and run git commands without the
   earlier failures (see Decisions above). Will drop from this list at
   the next update.
2. **No git commits made yet.** Repo is initialized; bash can now run
   git directly against it, so the earlier "commit from Ken's own
   machine" workaround may no longer be necessary — but no commit has
   been made, and Ken hasn't asked for one yet. Added 2026-07-07.
3. **`.odt` ingestion code's original authorship is still unconfirmed**
   (functionally fine and now explicitly wanted — see Decisions above).
   Low priority, informational only. Added 2026-07-07 (carried over from
   a prior session).
4. ~~`MANIFEST.txt`'s bundle hash doesn't match current on-disk
   content~~ **RESOLVED 2026-07-08** — Ken asked for the manifest to be
   regenerated treating current disk state as ground truth (clean-start
   basis, not a reconciliation of the old discrepancy). Ran
   `generate_manifest.py`; new bundle `e6837f143034ac15d9e3f8f0`;
   `verify_install.py` now reports all files + bundle OK. The root cause
   of the original mismatch was never identified — worth watching for a
   recurrence, but not blocking. Will drop from this list at the next
   update.

## 7. Next Steps

1. Make an initial git commit — repo is initialized with zero commits;
   bash can now run git directly in this project, so this no longer
   requires switching to Ken's own machine unless he prefers to.
2. Decide which "Known limitations" to prioritize next, if any: heading
   rendering, move labeling, background-corrected similarity, or table
   support — none requested yet, all documented as deliberate v1 scope
   cuts in `docs/API.md`.
3. Consider a dedicated `.docx` ingestion test file (`test_ingest_odt.py`
   exists; there's no `test_ingest_docx.py` equivalent, though
   `test_cli.py` and manual verification both exercise `compare_docx`).

## 8. Last Updated

2026-07-08T13:26:00Z | Trigger: manual | Staleness: **Fresh** (0 sections
substantially rewritten — file scan confirmed Architecture, Goals, and
Overview still match reality exactly; only Recent Decisions, Open
Questions, and Next Steps changed). This pass: the bash sandbox mount bug
in Open Question #1 no longer reproduces (resolved), and the
`MANIFEST.txt` bundle mismatch flagged earlier today was cleared per
Ken's request to regenerate treating current disk state as ground truth
— new bundle `e6837f143034ac15d9e3f8f0`, `verify_install.py` all OK, 38
tests passing. `git log` was empty (repo initialized, zero commits), so
weighting shifted to file scan + conversation context, per procedure.
