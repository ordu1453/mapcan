"""Точка входа mapcan-app.exe (окно редактора, без консоли)."""

import sys

from mapcan.launcher import main

if __name__ == "__main__":
    sys.exit(main())
