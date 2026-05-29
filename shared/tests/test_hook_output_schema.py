"""Meta-test: every hook that emits ``hookSpecificOutput`` sets ``hookEventName``.

Claude Code's hook protocol requires the ``hookSpecificOutput`` object to carry
a ``hookEventName`` field (e.g. ``"UserPromptSubmit"``, ``"SessionStart"``,
``"PostToolUse"``). A ``hookSpecificOutput`` emitted without it is rejected at
runtime with::

    Hook JSON output validation failed — hookSpecificOutput is missing
    required field "hookEventName"

This is invisible to ordinary unit tests (the hook still exits 0; the rejection
happens in the host). This AST drift-guard fails closed instead: it walks every
hook script under ``shared/scripts/hooks`` and ``plugins/*/scripts/hooks`` and
asserts that every ``{"hookSpecificOutput": {...}}`` dict-literal whose value is
itself a dict-literal includes a ``hookEventName`` key.

AST-based (not text/grep) so it ignores the field name appearing in comments or
docstrings — only real dict literals count. Origin:
iterate-2026-05-29-fix-suggest-iterate-hookeventname.
"""

from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _hook_files() -> list[Path]:
    roots = [_REPO / "shared" / "scripts" / "hooks"]
    roots += sorted((_REPO / "plugins").glob("*/scripts/hooks"))
    files: list[Path] = []
    for root in roots:
        if root.is_dir():
            files.extend(sorted(root.glob("*.py")))
    return files


def _violations_in(path: Path) -> list[str]:
    """Return descriptions of hookSpecificOutput dict-literals missing
    a non-empty ``hookEventName`` string key."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover - a broken hook is a different test's job
        return []
    out: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if not (isinstance(key, ast.Constant) and key.value == "hookSpecificOutput"):
                continue
            # Only inspect inline dict literals — a computed value (variable,
            # call) is out of static reach and the hook owns its own contract.
            if not isinstance(value, ast.Dict):
                continue
            inner = {
                k.value: v
                for k, v in zip(value.keys, value.values)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            hen = inner.get("hookEventName")
            if hen is None:
                out.append(f"{path.name}:{key.lineno} hookSpecificOutput has no hookEventName")
            elif isinstance(hen, ast.Constant) and (
                not isinstance(hen.value, str) or not hen.value.strip()
            ):
                out.append(
                    f"{path.name}:{key.lineno} hookEventName is empty/non-string"
                )
    return out


def test_hook_files_discovered():
    """Guard the guard: the scan actually finds hook scripts."""
    files = _hook_files()
    assert files, "no hook scripts discovered — scan roots are wrong"
    assert any(f.name == "suggest_iterate.py" for f in files)


def test_every_hookspecificoutput_sets_hookeventname():
    """Every emitted ``hookSpecificOutput`` dict-literal carries ``hookEventName``."""
    violations: list[str] = []
    for f in _hook_files():
        violations.extend(_violations_in(f))
    assert not violations, (
        "hookSpecificOutput dict-literal(s) missing required `hookEventName` "
        "(Claude Code rejects these at runtime):\n  - "
        + "\n  - ".join(violations)
    )
