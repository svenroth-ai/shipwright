"""Entry point so `python -m shared.scripts.dev_server <args>` works.

Mirrors the pre-split `if __name__ == "__main__": sys.exit(main())` at
the bottom of the original `dev_server.py`. The shim file at
`shared/scripts/dev_server.py` also routes through `main()` so
`uv run shared/scripts/dev_server.py <args>` is unchanged.
"""

from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
