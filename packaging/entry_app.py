"""Entry point of mapcan-app.exe (the editor window, without a console)."""

import sys

from mapcan.launcher import main

if __name__ == "__main__":
    sys.exit(main())
