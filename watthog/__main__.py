"""Точка входа для `python -m watthog`."""

import sys

from watthog.cli import main

if __name__ == "__main__":
    sys.exit(main())
