#!/usr/bin/env python3
"""Re-check external review key availability.

Used by the skill after the user indicates they've added an API key to
``.env.local`` in response to the Branch B "missing_keys" prompt.
Returns a tiny JSON blob the LLM can parse without touching the env file.

Usage:
    uv run check-external-review-keys.py
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.config import load_global_config, get_external_review_status  # noqa: E402


def main() -> int:
    plugin_root = Path(__file__).resolve().parents[2]
    config = load_global_config(plugin_root)
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
