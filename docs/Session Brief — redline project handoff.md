# Session Brief — redline project handoff

Written for a successor session with no memory of this conversation. This
session's access to `C:\Users\nlgun\PortFiles\NLGFiles\Software2026\redline` became unreliable (see "Environment instability" below) — this brief is
written from conversation memory only, not verified against current disk
state. **Re-verify everything against the actual files before trusting it.**

---

## What this project is

A lightweight, dependency-minimal Python package that redlines large,
heavily-revised documents (legal contracts especially) — producing `<ins>`/`<del>` HTML output like Word's "Compare Documents," but designed
specifically to avoid two failure modes Word and LibreOffice Writer both
have: cascading false positives from one early edit, and unreadable
word-salad diffs on heavily-rewritten paragraphs. Confirmed via research
that Word's Compare runs a flat Myers O(ND) diff with no anchor pre-pass
and no move detection — that's the specific gap this project targets.

## Design, condensed

Two phases, arrived at over a long back-and-forth (see "How we got here"
below if you want the reasoning, not just the conclusion):

**Phase 0 — exact/near-exact block removal (`blocks.py`).** A "block" is
at least a paragraph — Ken specifically corrected an earlier, more complex
word-level sliding-window design on this point. Because paragraph
boundaries are structural (given, not discovered), there's no
minimum-length parameter to calibrate — this is why an earlier, fairly
involved detour into information-theoretic entropy-rate math (Shannon
entropy, Asymptotic Equipartition Property) to justify a match-length
floor turned out to be unnecessary once this correction landed. Each
paragraph is hashed under an ordered transform ladder: exact text, then
whitespace-normalized, then case-folded. A match at a rung tells you
exactly what changed, at the cost of one exact-match pass — no need to
pay for Phase 1 to rediscover it. **Important, deliberate design point:
whitespace-only differences are treated as true non-changes (hidden);
case-only differences are classified cheaply here but must still render
as a visible diff**, because in a legal document "Agreement" vs.
"agreement" can be meaningful. A real bug was caught during testing where `render.py` was silently hiding case changes — fixed by giving `Block` both `text_a` and `text_b` instead of just one side's text.

Duplicate paragraphs are matched in position order by default (confirmed
rare and not worth heavy machinery, given block size). When a duplicate
would force a crossing (inconsistent) match, it's resolved via a
longest-increasing-subsequence pass — the conflicting match is dropped
back to "unmatched" rather than guessed.

**Phase 1 — recursive coarse-to-fine matching (`align.py`), on whatever
Phase 0 couldn't resolve.** Granularity ladder: paragraph → sentence →
word. Key simplification: once Phase 0's blocks are in order, they anchor
both documents into a shared spine — the hole between block *i* and
block *i+1* in doc A corresponds, by construction, to the hole between
the same two blocks in doc B. This means Phase 1 never needs a
whole-document candidate search, only a per-hole one, which is much
cheaper. Within a hole: `difflib`'s own ratio (staged behind the cheap `real_quick_ratio()`/`quick_ratio()` upper bounds before paying for the
real one) is the stopping test — if a pair is legible enough, accept it;
if not and it's still splittable, recurse to the next granularity via a
small Needleman-Wunsch-style alignment DP scored by Jaccard word-overlap.

## How we got here (only if you need the reasoning, not just the result)

Roughly in order: started from a generic "diff large documents" ask →
explored stochastic/fuzzy block matching (Jaccard, MinHash, bigram
significance scoring à la Dunning's G-test) → a detour into recursive
multi-resolution matching (citing FastDTW as precedent) → an
information-theoretic argument for minimum match length (Shannon entropy
rate / AEP) that got mostly obsoleted once Ken fixed block granularity at
paragraph-or-larger → an independent **Opus review** (dispatched via the
Agent tool specifically because the entropy-calibration question was a
genuinely contestable judgment call) that confirmed the two-phase
architecture but called the entropy math over-engineered and flagged
whole-document assignment/move-handling as the real hard problem — which
the "anchored spine" insight later mostly resolved. A "collaborating
agent nodes" idea was explicitly considered and rejected in favor of a
simpler stateless ensemble approach (precedent: T-Coffee/M-Coffee
consensus alignment in bioinformatics), on the grounds that agents would
add coordination overhead for what's fundamentally a scoring/DP problem.

**Ken's standing preferences, worth carrying forward:** calibrate
edge-case effort to actual likelihood rather than building machinery for
rare cases (a specific correction — don't repeat the mistake of
over-engineering duplicate-paragraph handling); surface inferences
inline as "I'm assuming X" without turning it into a slowdown; apply `ken-code-quality` (prefer simple, <30-line functions, <600-line files,
plan-before-code — though for this project the long design conversation
plus an explicit "proceed" already satisfied that gate once), plus `code-documentation-writing` and `test-guide` skills, which is why the
package has `docs/README.md`, `docs/CHEATSHEET.md`, `docs/API.md`, `docs/workflows.md`, and `TEST_GUIDE.md` alongside the code. Both are
captured in this Cowork account's persistent memory already, not just
this chat.

## Implementation status (as last verified working, before instability hit)

Package: `redline/{__init__,text,hashing,blocks,similarity,align,ingest,render,pipeline}.py`.
30 tests across `tests/test_{text,blocks,align,pipeline}.py` plus `tests/test_ingest_odt.py` all passed; `MANIFEST.txt` verified clean via `verify_install.py` at bundle hash `63b032acd280198ed53817e4` (before a
final small edit — see below).

Documented, deliberate gaps (in `docs/API.md` "Known limitations", not
oversights): tables aren't read from `.docx`/`.odt`; heading style names
are extracted but not threaded through to render as `<h1>`-`<h6>`; no
native Word tracked-changes handling; no explicit "moved from/to" label
(a relocated block renders as clean delete+insert); similarity scoring
is plain Jaccard, not the background-corrected (document-frequency
weighted) version discussed as a possible refinement for telling apart
near-duplicate boilerplate clauses.

## The .odt mystery — needs resolving, not just accepting

Ken asked this session to add `.odt` support. Before any code was
written, `redline/ingest.py:from_odt`, `redline/pipeline.py:compare_odt`,
the `__init__.py` export, and `tests/test_ingest_odt.py` were all already
present, fully working (all tests passed), and already reflected in `docs/*.md` and `MANIFEST.txt`. This was **not written in this
conversation** — nobody in this session has a record of authoring it.
It closely matches this project's conventions (docstring style, the `ImportError` + pip-install-hint pattern mirroring `from_docx`, "Heading
N" naming). Ken did not confirm whether he wrote it himself or it came
from elsewhere. **Ask him directly before building on it further** —
functionally it looks fine, but the provenance is unverified.

One real gap found and fixed in this session: `pyproject.toml`'s `[project.optional-dependencies]` had `docx` but not `odt`, even though
the feature was fully implemented and documented. Added:

```toml
[project.optional-dependencies]
docx = ["python-docx>=1.0"]
odt = ["odfpy>=1.4"]
```

**Whether this edit actually landed correctly on disk is unconfirmed** —
see next section.

## Environment instability this session — read before trusting any file read

Two separate incidents, worth being cautious about rather than assuming
resolved:

1. Mid-session, `bash`'s view of the entire `redline` mount went empty —
   no files at all — while Ken confirmed via `dir` on his actual machine
   that everything was intact. Retrying didn't fix it. Root cause
   undetermined; resolved (for read purposes) by reconnecting the folder
   via `request_cowork_directory`, after which `Glob`/`Read` could see
   the real contents again.

2. After reconnecting, editing `pyproject.toml` via the `Edit` tool to
   add the `odt` optional-dependency line: `Read` immediately afterward
   showed a complete, correct 15-line file. But `bash` (`xxd`, `wc -c`)
   showed the file truncated at 303 bytes, cut off mid-array
   (`testpaths = ["tests"` with no closing bracket, `pythonpath` line
   missing entirely) — which is what broke `pytest`'s TOML parser. **`Read` and `bash` disagreed about actual file content, a second time
   this session, in a different way than incident 1.** Per this
   project's own working principle ("bash is ground truth for file
   state" — from `reflection-guidelines`), bash's version should be
   trusted, meaning the file was likely genuinely broken on disk at that
   point. Ken said "don't touch the folder" before a fix was attempted,
   so **`pyproject.toml` may currently still be in a truncated,
   syntactically invalid state.**

Known-good content to restore it to, if it's still broken:

```toml
[project]
name = "redline"
version = "0.1.0"
description = "Lightweight document redlining for large, heavily-revised documents"
requires-python = ">=3.10"
dependencies = []

[project.optional-dependencies]
docx = ["python-docx>=1.0"]
odt = ["odfpy>=1.4"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

**Recommendation for the successor session:** don't trust a single
tool's read of this folder without cross-checking against another (bash
vs. Read/Glob), and if they still disagree, ask Ken to confirm via `dir` or `type` on his machine directly, the way this session had to. After
any fix, regenerate `MANIFEST.txt` (`python3 generate_manifest.py`) and
re-run `pytest tests/ -q` before considering anything settled. There's
also an initialized-but-empty git repo in the folder (zero commits, and
a stray `.git/index.lock` was seen at one point) — worth committing once
the folder's state is confirmed trustworthy again.

## Immediate next steps

1. Confirm with Ken the actual current state of the folder (don't assume
   this brief's account is still accurate — environment was unstable).
2. Resolve the `.odt` authorship question before trusting or extending
   that code further.
3. Fix `pyproject.toml` if still broken; regenerate manifest; re-run
   full test suite.
4. Make an initial git commit — repo exists, nothing committed yet.
5. Ask Ken which "Known limitations" (heading rendering, move labeling,
   background-corrected similarity, table support) he wants prioritized
   next, if any — none were requested yet, all are documented as
   deliberate v1 scope cuts.
