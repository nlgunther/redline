"""Lightweight document redlining for large, heavily-revised documents.

See docs/README.md for the quick start and docs/API.md for the full
reference. The short version:

    from redline import compare_text, compare_docx, compare_odt
    html = compare_text(old_text, new_text)

A command-line interface is also available -- see docs/CHEATSHEET.md or
run `redline --help` (after `pip install -e .`) / `python -m redline --help`.
"""

try:
    from importlib.metadata import version as _pkg_version

    __version__ = _pkg_version("redline")
except Exception:
    # Not installed as a distribution (e.g. running straight from source) --
    # fall back to the version pinned in pyproject.toml. Keep these in sync.
    __version__ = "0.1.0"

from .pipeline import compare_text, compare_docx, compare_odt, compare_pdf

__all__ = ["compare_text", "compare_docx", "compare_odt", "compare_pdf", "__version__"]
