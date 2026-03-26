#!/usr/bin/env python3
"""Validate that Aikido Security credentials are available.

Run as a SessionStart hook to give early feedback if credentials are missing.
Outputs structured JSON for Claude to display as a setup hint.
"""

from __future__ import annotations

import io
import json
import os
import sys
from pathlib import Path

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PLUGIN_ROOT = Path(__file__).parent.parent.parent
ENV_FILE = PLUGIN_ROOT / ".env"
SETUP_URL = "https://app.aikido.dev/settings/integrations/api/aikido/rest"


def load_env_file() -> None:
    """Load environment variables from .env file."""
    if not ENV_FILE.exists():
        return
    try:
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception:
        pass


def main() -> int:
    load_env_file()

    client_id = os.environ.get("AIKIDO_CLIENT_ID", "")
    client_secret = os.environ.get("AIKIDO_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": (
                    "Aikido Security: credentials not configured. "
                    "Security scanning is available but requires setup.\n"
                    f"1. Create API credentials at {SETUP_URL}\n"
                    f"2. Add AIKIDO_CLIENT_ID and AIKIDO_CLIENT_SECRET to {ENV_FILE}\n"
                    "3. See skills/security/references/setup-guide.md for details."
                ),
            }
        }
        print(json.dumps(output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
