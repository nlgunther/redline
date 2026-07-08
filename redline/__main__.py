"""Enables `python -m redline ...` without requiring the package to be
installed as a console script."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
