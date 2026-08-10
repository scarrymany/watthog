"""Точка входа для `python -m watthog.gui`."""

import sys

from watthog.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
