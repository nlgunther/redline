# redline — Common Workflows

## Workflow 1: Redline two plain-text drafts and save to a file

You have two `.txt` drafts of a contract and want a redline you can open
in a browser.

```python
from redline import compare_text

with open("draft_v1.txt") as f:
    old = f.read()
with open("draft_v2.txt") as f:
    new = f.read()

html = compare_text(old, new)
with open("redline.html", "w") as f:
    f.write(html)
```

### Result
`redline.html` opens in any browser; unchanged paragraphs appear plain,
edits appear inline with strikethrough/underline, whole new or removed
paragraphs appear as full insertions/deletions. See `docs/API.md` for the
`compare_text` reference.

## Workflow 2: Redline two Word documents

```python
from redline import compare_docx

html = compare_docx("Agreement_v1.docx", "Agreement_v2.docx")
with open("Agreement_redline.html", "w") as f:
    f.write(html)
```

### Result
Same output as Workflow 1. Requires `pip install python-docx`. Table
content is not currently compared — see `docs/API.md` "Known
limitations" if the documents rely heavily on tables.

## Workflow 3: Redline two OpenDocument (.odt) files

Same shape as the Word workflow -- LibreOffice/OpenOffice users can use
this instead of converting to .docx first.

```python
from redline import compare_odt

html = compare_odt("Agreement_v1.odt", "Agreement_v2.odt")
with open("Agreement_redline.html", "w") as f:
    f.write(html)
```

### Result
Same output shape as Workflows 1 and 2. Requires `pip install odfpy`.
Table content is not compared, same limitation as the .docx path.

## Workflow 4: Inspect what Phase 0 found before running the full compare

Useful when tuning or debugging — e.g. checking how much of a document
was recognized as unchanged before paying for Phase 1.

```python
from redline.ingest import from_text
from redline.blocks import find_blocks

paras_a = [p.text for p in from_text(old_text)]
paras_b = [p.text for p in from_text(new_text)]

blocks, unmatched_a, unmatched_b = find_blocks(paras_a, paras_b)

covered = sum(len(b.index_a) for b in blocks)
print(f"{covered}/{len(paras_a)} paragraphs matched exactly or near-exactly")
for b in blocks:
    if b.transform != "exact":
        print(f"  paragraph {b.index_a.start}: {b.transform}-only change")
```

### Result
A quick sense of how much of the document Phase 0 disposed of before the
more expensive recursive matcher runs on the rest — and a list of any
paragraphs that changed only in whitespace or case, which are otherwise
invisible or subtle in the final HTML. See `docs/API.md` for
`find_blocks` and the `Block` fields.

## Workflow 5: Redline two documents from the command line

You don't want to write Python at all — just run one command and get an
HTML file, e.g. from a shell script or a CI step.

```bash
pip install -e .   # once, to register the `redline` command
redline Agreement_v1.docx Agreement_v2.docx -o Agreement_redline.html
```

Format is auto-detected from the first file's extension. Mixing formats,
or files without an extension, need an explicit flag:

```bash
redline draft_old draft_new --format docx -o redline.html
```

Piping instead of writing a file (format still auto-detected):

```bash
redline old.txt new.txt | tee redline.html
```

Without installing the package, the same command works via `python -m`:

```bash
python -m redline Agreement_v1.docx Agreement_v2.docx -o Agreement_redline.html
```

### Result
Same HTML output as Workflows 1-3. A missing file or missing optional
dependency (`python-docx`/`odfpy`) prints a one-line error to stderr and
exits with code `1`, rather than a Python traceback — see `docs/API.md`
"Module: `redline.cli`" for the full exit-code reference.
