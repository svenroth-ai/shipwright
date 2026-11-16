"""Claude Code plugin signal of the stack signature (matching key of the ``claude-plugin`` profile).

A ``.claude-plugin/`` FOLDER at the repository root (a plugin or a marketplace) or exactly one level
down under ``plugins/*/`` (a plugin monorepo) adds the runtime key ``claude-plugin`` and the signal
``has-claude-plugin-dir``. The profile matcher scores profiles by the dependency names they declare
under ``stack``; the ``claude-plugin`` profile declares this key, so it outscores the generic Python
profile for a plugin repository, while a Python-only repository without the folder keeps the generic one.
Only for a Python repository (``runtime`` has ``python``): the promoted profile carries Python commands, CI and
CodeQL, so a markdown-only or TypeScript plugin keeps the match it had (typically ``generic``).
A file of that name, a deeper folder or a folder outside ``plugins/`` is not a signal.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

RUNTIME_KEY = "claude-plugin"
SIGNAL = "has-claude-plugin-dir"


def add_plugin_signal(stack: dict[str, Any], project_root: Path, excludes: set[str] | None = None) -> dict[str, Any]:
    """Add the signal to ``stack`` (a ``detect_stack`` result) in place and return it."""
    def excluded(d: Path) -> bool:  # same rule as stack_detector: an excluded path or anything below it
        rel = d.relative_to(project_root).as_posix()
        return any(rel == e or rel.startswith(e + "/") for e in (excludes or ()))

    if "python" not in stack.get("runtime", {}):  # the profile it promotes is a Python toolchain: no Python, no signal
        return stack
    dirs = [project_root / ".claude-plugin", *sorted(project_root.glob("plugins/*/.claude-plugin"))]
    if any(d.is_dir() and not excluded(d) for d in dirs):
        stack.setdefault("runtime", {})[RUNTIME_KEY] = ".claude-plugin/"
        signals = stack.setdefault("signals", [])
        if SIGNAL not in signals:
            signals.append(SIGNAL)
    return stack
