import hashlib, os
from datetime import datetime, timezone

FILES = [
    ("redline/__init__.py", None),
    ("redline/text.py", None),
    ("redline/hashing.py", None),
    ("redline/blocks.py", None),
    ("redline/similarity.py", None),
    ("redline/align.py", None),
    ("redline/ingest.py", None),
    ("redline/render.py", None),
    ("redline/pipeline.py", None),
    ("redline/cli.py", None),
    ("redline/__main__.py", None),
    ("tests/__init__.py", None),
    ("tests/test_text.py", None),
    ("tests/test_blocks.py", None),
    ("tests/test_align.py", None),
    ("tests/test_pipeline.py", None),
    ("tests/test_ingest_odt.py", None),
    ("tests/test_cli.py", None),
    ("pyproject.toml", None),
    ("verify_install.py", None),
]

def sha16(data: bytes) -> str:
    n = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    return hashlib.sha256(n).hexdigest()[:16]

def bundle_hash(file_hashes: dict[str, str]) -> str:
    concatenated = "".join(sha for _, sha in sorted(file_hashes.items()))
    return hashlib.sha256(concatenated.encode()).hexdigest()[:24]

rows = {}
for lp, op in FILES:
    src = op or lp
    if not os.path.exists(src):
        rows[lp] = "MISSING"; continue
    with open(src, "rb") as f: data = f.read()
    rows[lp] = sha16(data)

bundle = bundle_hash({p: s for p, s in rows.items() if s != "MISSING"})
ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

lines = [
    "# redline file manifest",
    "# Generated: %s" % ts,
    "# Format:  sha256_prefix<TAB>local_path",
    "# Comments (lines starting with #) and blank lines are ignored.",
    "# Update only the hash values when files change.",
    "# verify_install.py reads this file -- do not change the format.",
    "# Note: hashes computed with CRLF normalisation (Windows-compatible).",
    "# Bundle: SHA-256 of sorted file hashes concatenated (hash-of-hashes).",
    "#",
    "bundle:\t%s" % bundle,
    "#", "# Source files",
]
for lp, sha in rows.items():
    lines.append(("# MISSING\t%s" if sha == "MISSING" else "%s\t%s") % (sha, lp))

tc = sum(
    sum(1 for l in open(op or lp) if l.strip().startswith("def test_"))
    for lp, op in FILES
    if (op or lp).startswith("tests/test_") and os.path.exists(op or lp)
)
if tc:
    lines += ["#", "# Tests: %d methods" % tc]

with open("MANIFEST.txt", "w") as f:
    f.write("\n".join(lines) + "\n")
print("Bundle hash: %s" % bundle)
print("Tests: %d" % tc)
