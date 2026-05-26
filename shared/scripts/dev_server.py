#!/usr/bin/env python3
"""Re-export shim — the dev_server implementation moved to a package.

The original 997-LOC monolith was split in B4 (campaign
`2026-05-25-bloat-cleanup-B-shipwright`) into the `dev_server/` package
sibling of this file. This shim exists ONLY so existing callers that
invoke `uv run shared/scripts/dev_server.py <args>` keep working —
Python's import machinery prefers the `dev_server/` package directory
over this file (verified empirically), so `import dev_server` from
tests resolves to the package, not this file.

Public surface: see `shared/scripts/dev_server/__init__.py` and
`docs/hooks-and-pipeline.md`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add this script's parent dir to sys.path so `import dev_server` finds
# the package (`shared/scripts/dev_server/`) when invoked as a top-level
# script via `uv run`.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dev_server import main  # noqa: E402  -- routed through package

if __name__ == "__main__":
    sys.exit(main())
