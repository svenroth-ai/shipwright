#!/usr/bin/env python3
"""Validate that a security scanner backend is available.

Run as a SessionStart hook to give early feedback if no backend is configured.
Supports both Aikido (cloud) and OSS (Semgrep/Trivy/Gitleaks) backends.
Outputs structured JSON for Claude to display as a setup hint.
"""

from __future__ import annotations

import io
import json
import os
import shutil
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

OSS_TOOLS = {
    "semgrep": {
        "type": "SAST",
        "install_win": "pip install semgrep",
        "install_mac": "brew install semgrep",
        "url": "https://semgrep.dev/docs/getting-started/",
    },
    "trivy": {
        "type": "SCA",
        "install_win": "winget install AquaSecurity.Trivy",
        "install_mac": "brew install trivy",
        "url": "https://github.com/aquasecurity/trivy/releases",
    },
    "gitleaks": {
        "type": "Secrets",
        "install_win": "winget install Gitleaks.Gitleaks",
        "install_mac": "brew install gitleaks",
        "url": "https://github.com/gitleaks/gitleaks/releases",
    },
}


def _format_install_hint(tool: str) -> str:
    """Format a multi-line install hint for a single tool."""
    info = OSS_TOOLS[tool]
    is_win = sys.platform == "win32"
    if is_win:
        return (
            f"  {tool} ({info['type']}):\n"
            f"    Windows: {info['install_win']}\n"
            f"    Download: {info['url']}"
        )
    return (
        f"  {tool} ({info['type']}):\n"
        f"    macOS: {info['install_mac']}\n"
        f"    Download: {info['url']}"
    )


def _detect_backend() -> str | None:
    """Detect which backend is available. Returns 'aikido', 'oss', or None."""
    explicit = os.environ.get("SHIPWRIGHT_SCANNER_BACKEND", "").lower()
    if explicit in ("aikido", "oss"):
        return explicit

    if os.environ.get("AIKIDO_CLIENT_ID") and os.environ.get("AIKIDO_CLIENT_SECRET"):
        return "aikido"

    if any(shutil.which(tool) for tool in OSS_TOOLS):
        return "oss"

    return None


def _oss_status() -> dict[str, bool]:
    """Check which OSS tools are available."""
    return {tool: shutil.which(tool) is not None for tool in OSS_TOOLS}


def main() -> int:
    load_shipwright_env()

    backend = _detect_backend()

    if backend == "aikido":
        # Aikido is configured — all good
        return 0

    if backend == "oss":
        # OSS backend — report which tools are available
        status = _oss_status()
        available = [f"{OSS_TOOLS[t]['type']} ({t})" for t, ok in status.items() if ok]
        missing = [t for t, ok in status.items() if not ok]

        if missing:
            missing_hints = [_format_install_hint(t) for t in missing]
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": (
                        f"Security scanner: OSS backend active. Available: {', '.join(available)}.\n"
                        f"Optional — install missing tools for broader coverage:\n\n"
                        + "\n".join(missing_hints)
                    ),
                }
            }
            print(json.dumps(output))
        return 0

    # No backend configured at all
    oss_hints = [_format_install_hint(t) for t in OSS_TOOLS]

    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                "Security scanning: no backend configured.\n\n"
                "Option A — OSS (local, free):\n"
                "Install at least one of these tools:\n\n"
                + "\n".join(oss_hints) + "\n\n"
                "Option B — Aikido (cloud SaaS):\n"
                f"1. Create API credentials at {SETUP_URL}\n"
                "2. Add AIKIDO_CLIENT_ID and AIKIDO_CLIENT_SECRET to <project>/.env.local\n"
                "3. See skills/security/references/setup-guide.md"
            ),
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
