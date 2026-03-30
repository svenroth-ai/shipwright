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
SHARED_SCRIPTS = PLUGIN_ROOT.parent.parent / "shared" / "scripts"
SETUP_URL = "https://app.aikido.dev/settings/integrations/api/aikido/rest"

sys.path.insert(0, str(SHARED_SCRIPTS / "lib"))
from env import load_shipwright_env


def main() -> int:
    load_shipwright_env()

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
                    "2. Add AIKIDO_CLIENT_ID and AIKIDO_CLIENT_SECRET to <shipwright_root>/.env.local\n"
                    "3. See skills/security/references/setup-guide.md for details."
                ),
            }
        }
        print(json.dumps(output))

    return 0


if __name__ == "__main__":
    sys.exit(main())
