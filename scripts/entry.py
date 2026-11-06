"""PyInstaller entry point for the standalone executable."""

import sys

from speakeasy_scribe.cli import main

if __name__ == "__main__":
    sys.exit(main())
