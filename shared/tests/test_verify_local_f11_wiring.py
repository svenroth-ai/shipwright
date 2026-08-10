"""F11 must re-run the local CI-gate mirror on the regenerated pre-push tree.

F0 is deliberately an early check.  It cannot inspect tracked finalization artifacts
or an ``ensure_current`` merge that happens later.  F11 is the only local point where
the merged, regenerated commit exists before it is pushed for CI to judge.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ITERATE_SKILL = _REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
_F11 = _ITERATE_SKILL / "references" / "F11.md"
_SKILL_MD = _ITERATE_SKILL / "SKILL.md"
_HOOKS_DOC = _REPO_ROOT / "docs" / "hooks-and-pipeline.md"
_VERIFY_LOCAL = _REPO_ROOT / "scripts" / "verify_local.py"

_MARKER = "SHIPWRIGHT_MIRRORED_MERGE_GATES"


def _f11_text() -> str:
    return _F11.read_text(encoding="utf-8")


def _f11_gate_block() -> str:
    blocks = re.findall(r"```[a-zA-Z]*\n(.*?)```", _f11_text(), re.DOTALL)
    matches = [
        block
        for block in blocks
        if re.search(
            r'^\s*\(\s*cd\s+"\{project_root\}"\s+&&\s+'
            r'uv\s+run\s+scripts/verify_local\.py\s*\)\s*\|\|\s*\{\s*$',
            block,
            re.MULTILINE,
        )
    ]
    assert len(matches) == 1, (
        "F11 must contain exactly one executable re-check of scripts/verify_local.py; "
        f"found {len(matches)}."
    )
    return matches[0]


def _assert_fail_closed_gate(block: str) -> None:
    """Assert the exact shell shape, excluding comments, prose, and ``echo``."""
    executable = [
        line.strip()
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    command = re.compile(
        r'^\(\s*cd\s+"\{project_root\}"\s+&&\s+'
        r'uv\s+run\s+scripts/verify_local\.py\s*\)\s*\|\|\s*\{$'
    )
    command_index = next(
        (index for index, line in enumerate(executable) if command.fullmatch(line)),
        None,
    )
    assert command_index is not None, (
        "F11 must execute the exact verify_local.py command under a fail-closed "
        "handler; prose, comments, and echo do not execute the gate."
    )
    assert any("-f" in line for line in executable[:command_index]), (
        "F11 must check that the monorepo-only local gate exists before executing it."
    )
    assert any("grep -q" in line and _MARKER in line for line in executable[:command_index]), (
        "F11 must identify Shipwright's own local gate before executing it; a path-only "
        "check could run an unrelated consumer script under STOP semantics."
    )
    handler = executable[command_index + 1 :]
    close_index = next((index for index, line in enumerate(handler) if line == "}"), None)
    assert close_index is not None and "exit 1" in handler[:close_index], (
        "A non-zero F11 local-gate verdict must exit from its own handler before push; "
        "a later unrelated exit is not fail-closed."
    )


def test_f11_runs_the_guarded_local_gate() -> None:
    """The F11 call is an executable STOP gate, not an aspirational mention."""
    _assert_fail_closed_gate(_f11_gate_block())


def test_f11_gate_rejects_prose_and_a_fall_through_handler() -> None:
    """Protect the test itself from accepting superficially similar documentation."""
    block = _f11_gate_block()
    prose_only = block.replace(
        '( cd "{project_root}" && uv run scripts/verify_local.py ) || {',
        'echo \'( cd "{project_root}" && uv run scripts/verify_local.py ) || {\'',
    )
    with pytest.raises(AssertionError, match="exact verify_local.py command"):
        _assert_fail_closed_gate(prose_only)

    fall_through = block.replace("      exit 1\n    }\n  else", "    }\n  else")
    with pytest.raises(AssertionError, match="its own handler"):
        _assert_fail_closed_gate(fall_through)


def test_f11_marker_inspection_error_stops_instead_of_skipping() -> None:
    """Only a missing marker may no-op; a grep read error must block the push."""
    block = _f11_gate_block()
    assert "grep_status=$?" in block
    assert 'if [ "$grep_status" -ne 1 ]; then' in block
    assert 'echo "STOP: F11 could not inspect the local CI-gate mirror marker."' in block
    inspection_handler = block.split("grep_status=$?", maxsplit=1)[1]
    assert "exit 1" in inspection_handler, (
        "A marker-inspection error must STOP rather than silently behaving like an "
        "unmarked consumer script."
    )


def test_f11_gate_runs_after_integration_and_before_push() -> None:
    """The re-check is useful only for the post-regeneration, pre-push snapshot."""
    text = _f11_text()
    integrated = text.index('\necho "$guard"\n')
    verified = text.index("uv run scripts/verify_local.py")
    pushed = text.index('git -C "{project_root}" push -u origin')
    assert integrated < verified < pushed, (
        "F11 must run verify_local.py after ensure_current has integrated and regenerated "
        "and before git push; any other placement validates the wrong tree."
    )


def test_f11_docs_state_the_accepted_late_stop() -> None:
    """Readers of every F11 summary must know this can stop after F6 committed."""
    f11 = _f11_text().lower()
    skill = _SKILL_MD.read_text(encoding="utf-8").lower()
    hooks = _HOOKS_DOC.read_text(encoding="utf-8").lower()
    script = _VERIFY_LOCAL.read_text(encoding="utf-8").lower()
    for name, text in {
        "F11.md": f11,
        "SKILL.md": skill,
        "hooks-and-pipeline.md": hooks,
        "verify_local.py": script,
    }.items():
        assert re.search(r"late(?:\s|\*|_)+stop", text), (
            f"{name} must say the F11 re-check can STOP after commit rather than "
            "implying F0 alone validates the pushed tree."
        )
