"""track_tool_calls.py must be untouched by the context-cost-meter diff
(operator instruction: land the new hook purely additively — cutover to
retire the tool-call-count proxy is an explicit, separate follow-up
iterate). Reuses test_phase_plugin_hooks_consistency's own manifest
parsing so this stays byte-consistent with the SSoT that file already
maintains, rather than re-implementing hooks.json parsing a second time.
"""

from __future__ import annotations

from pathlib import Path

# A relative import, not a sys.path insertion: shared/tests/__init__.py makes
# this package-relative and avoids putting shared/tests itself on sys.path.
# That insertion (this file's previous approach) shadowed shared/scripts/
# tools with shared/tests/tools/ (a same-named, unrelated sibling test
# package -- test_validate_deploy_profile.py's home) for every OTHER test
# file collected afterward in the same session, breaking any deferred
# ``from tools...`` import wherever collection order put this file first
# (external-review-adjacent finding surfaced while fixing
# iterate-2026-08-07-context-cost-meter's review findings).
from .test_phase_plugin_hooks_consistency import _hook_commands, _load_hooks

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_track_tool_calls_still_registered_under_post_tool_use():
    hooks = _load_hooks("shipwright-build")
    cmds = _hook_commands(hooks.get("PostToolUse") or [])
    assert "track_tool_calls.py" in cmds, (
        "track_tool_calls.py's PostToolUse registration must survive this diff "
        "unmodified -- the context-cost meter lands additively, cutover is a "
        "separate follow-up iterate."
    )


def test_track_tool_calls_script_still_exists():
    path = REPO_ROOT / "shared" / "scripts" / "hooks" / "track_tool_calls.py"
    assert path.exists(), "track_tool_calls.py must not be deleted by this diff."


def test_context_cost_hook_is_additive_not_a_replacement():
    hooks = _load_hooks("shipwright-build")
    stop_cmds = _hook_commands(hooks.get("Stop") or [])
    post_tool_use_cmds = _hook_commands(hooks.get("PostToolUse") or [])
    # The new hook lives in Stop, the old one stays in PostToolUse -- distinct
    # arrays, neither entry displaced the other.
    assert "track_context_cost.py" in stop_cmds
    assert "track_tool_calls.py" in post_tool_use_cmds
    assert "track_tool_calls.py" not in stop_cmds
    assert "track_context_cost.py" not in post_tool_use_cmds
