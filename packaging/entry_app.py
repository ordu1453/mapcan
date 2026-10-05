"""Точка входа canmap-app.exe (окно редактора, без консоли)."""

import sys

from canmap.launcher import main

if __name__ == "__main__":
    sys.exit(main())
