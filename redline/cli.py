"""Command-line interface for redline.

Thin glue over redline.pipeline's compare_* functions: parse arguments,
figure out which comparison to run, write the HTML result. All actual
comparison logic lives in pipeline.py -- this module only handles argument
routing and I/O, per the project's "CLI is glue code" convention. See
docs/API.md "Module: redline.cli" for the full reference.
"""

import argparse
import sys
from pathlib import Path

from . import __version__
from .pipeline import compare_docx, compare_odt, compare_pdf, compare_text

# Maps a lowercased file suffix to the format name used everywhere else in
# this module. Anything not listed here (.txt, .md, no extension, ...)
# falls back to "text" -- see _resolve_format.
_FORMAT_BY_SUFFIX = {
    ".docx": "docx",
    ".odt": "odt",
    ".pdf": "pdf",
}


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns a process exit code: 0 on success, 1 if the comparison could
    not be completed (missing file, missing optional dependency, or an
    unreadable/corrupt document). Argument-parsing errors (bad flags,
    --help, --version) are handled by argparse itself, which exits the
    process directly with its own code (2, 0, 0 respectively).

    Example:
        main(["old.docx", "new.docx", "-o", "redline.html"])
        # -> 0, and redline.html now contains the comparison
    """
    args = _parse_args(argv)
    try:
        html = _compare(args.old, args.new, args.format)
    except Exception as exc:
        print(f"redline: {exc}", file=sys.stderr)
        return 1

    _write_output(html, args.output)
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="redline",
        description="Compare two documents and produce an HTML redline (<ins>/<del>).",
    )
    parser.add_argument("old", type=Path, help="path to the original document")
    parser.add_argument("new", type=Path, help="path to the revised document")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="write HTML here instead of stdout",
    )
    parser.add_argument(
        "-f", "--format", choices=["auto", "text", "docx", "odt", "pdf"], default="auto",
        help="input format (default: auto-detect from OLD's file extension)",
    )
    parser.add_argument("--version", action="version", version=f"redline {__version__}")
    return parser.parse_args(argv)


def _compare(old: Path, new: Path, fmt: str) -> str:
    """Validate both paths up front (regardless of format) so a missing
    file always produces the same clean message, rather than whatever
    exception python-docx/odfpy happen to raise for a bad path."""
    for path in (old, new):
        if not path.exists():
            raise FileNotFoundError(f"no such file: {path}")

    resolved = fmt if fmt != "auto" else _FORMAT_BY_SUFFIX.get(old.suffix.lower(), "text")
    if resolved == "docx":
        return compare_docx(old, new)
    if resolved == "odt":
        return compare_odt(old, new)
    if resolved == "pdf":
        return compare_pdf(old, new)
    return compare_text(old.read_text(encoding="utf-8"), new.read_text(encoding="utf-8"))


def _write_output(html: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(html)
    else:
        output.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
