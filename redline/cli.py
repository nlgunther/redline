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
        html = _compare(args.old, args.new, args.format, not args.suppress_moves)
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
    parser.add_argument(
        "--suppress-moves", action="store_true",
        help="render relocated content as a plain delete+insert instead of "
        "a labeled {moved above}/{moved below} pair (default: moves are detected)",
    )
    parser.add_argument("--version", action="version", version=f"redline {__version__}")
    return parser.parse_args(argv)


def _read_text_file(path: Path) -> str:
    """Read a plain-text file, tolerating the encodings Windows editors
    commonly produce.

    A ``.txt`` that started life in Word or Notepad is frequently saved as
    cp1252 ("ANSI") rather than UTF-8 -- smart quotes, em dashes, and
    accented characters all encode as bytes that are invalid UTF-8
    continuation bytes, so a plain ``read_text(encoding="utf-8")`` used to
    raise a raw UnicodeDecodeError with nothing but a byte offset to go on.
    Tried in order: UTF-8 with an optional BOM stripped (``utf-8-sig`` --
    also fixes a stray leading U+FEFF from Notepad's "UTF-8" save option,
    which would otherwise show up as an invisible extra character on the
    first paragraph), then cp1252 (Windows' historical default), which
    resolves the overwhelming majority of real-world cases without adding
    a charset-detection dependency to an otherwise lightweight CLI tool.

    Raises:
        ValueError: if the file decodes as neither -- e.g. it's actually
            binary data -- naming the file so the error isn't just a byte
            offset.

    Example:
        _read_text_file(Path("agreement.txt"))
        # -> "SIGNED: ..." (works whether the file is UTF-8 or cp1252)
    """
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        pass
    try:
        return path.read_text(encoding="cp1252")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"{path}: could not decode as UTF-8 or cp1252 (Windows ANSI) -- "
            f"file may be binary or use another encoding: {exc}"
        ) from exc


def _compare(old: Path, new: Path, fmt: str, detect_moves: bool = True) -> str:
    """Validate both paths up front (regardless of format) so a missing
    file always produces the same clean message, rather than whatever
    exception python-docx/odfpy happen to raise for a bad path."""
    for path in (old, new):
        if not path.exists():
            raise FileNotFoundError(f"no such file: {path}")

    resolved = fmt if fmt != "auto" else _FORMAT_BY_SUFFIX.get(old.suffix.lower(), "text")
    if resolved == "docx":
        return compare_docx(old, new, detect_moves)
    if resolved == "odt":
        return compare_odt(old, new, detect_moves)
    if resolved == "pdf":
        return compare_pdf(old, new, detect_moves)
    return compare_text(_read_text_file(old), _read_text_file(new), detect_moves)


def _write_output(html: str, output: Path | None) -> None:
    if output is None:
        sys.stdout.write(html)
    else:
        output.write_text(html, encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
