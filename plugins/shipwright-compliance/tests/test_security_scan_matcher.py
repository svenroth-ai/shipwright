"""Unit tests for the deploy-gate command matcher (``check_security_scan``).

The gate used to substring-match the raw command, so any unrelated command that
merely *mentioned* a deploy-family word inside a quoted argument value — e.g. an
iterate-finalization ``--justification "...deployed..."`` or an ``echo`` comment
— was wrongly soft-blocked. The matcher now reads the command STRUCTURE only
(quoted argument spans are stripped first); these tests pin both directions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HOOKS_DIR = Path(__file__).parent.parent / "scripts" / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
from check_security_scan import _is_deploy_command  # noqa: E402


@pytest.mark.parametrize("cmd", [
    # the exact false-block class: a deploy word only inside a quoted value
    'uv run surface_verification.py --justification "no status.json in any deployed flow"',
    'echo "=== no deploy-family words here ==="',
    "git commit -m 'deploy the new feature'",
    'uv run x.py --reason "this resolves the deploy gate"',
    # genuinely unrelated commands
    "npm test",
    "uv run pytest shared/tests/",
])
def test_quoted_prose_or_unrelated_does_not_trigger(cmd):
    assert _is_deploy_command(cmd) is False


@pytest.mark.parametrize("cmd", [
    "vercel",
    "vercel deploy",
    "jelastic env create",
    "fly deploy --remote-only",
    "railway up",
    "npm run deploy",
    "bash deploy.sh",
    "uv run plugins/shipwright-deploy/scripts/deploy.py",
])
def test_real_deploy_commands_still_trigger(cmd):
    assert _is_deploy_command(cmd) is True
