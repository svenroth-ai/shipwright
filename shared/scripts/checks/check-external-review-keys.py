#!/usr/bin/env python3
"""Re-check external review key availability (shared across all plugins).

Used by skills (plan, iterate, ...) after the user indicates they've added an
API key to ``.env.local`` in response to the "missing_keys" prompt. Returns a
small JSON blob the LLM can parse without touching the env file.

Usage:
    uv run shared/scripts/checks/check-external-review-keys.py
"""

import json
import os
import sys
from pathlib import Path

# Wire up shared/scripts/lib so we can import config helpers + env loader.
# parents[0]=checks, [1]=scripts, [2]=shared.
_SHARED_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_SHARED_LIB) not in sys.path:
    sys.path.insert(0, str(_SHARED_LIB))

from external_review_config import (  # noqa: E402
    get_external_review_status,
    load_review_config,
)


def main() -> int:
    config = load_review_config()
    status = get_external_review_status(config)

    providers = {
        "openrouter": bool(os.environ.get("OPENROUTER_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
    }

    print(json.dumps({
        "available": status == "available",
        "status": status,
        "providers": providers,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
