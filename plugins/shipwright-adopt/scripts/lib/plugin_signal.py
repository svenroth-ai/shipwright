"""Claude Code plugin signal of the stack signature (matching key of the ``claude-plugin`` profile).

A ``.claude-plugin/`` FOLDER at the repository root (a plugin or a marketplace) or exactly one level
down under ``plugins/*/`` (a plugin monorepo) adds the runtime key ``claude-plugin`` and the signal
``has-claude-plugin-dir``. The signal never enters a score (``profile_matcher.SIGNAL_KEYS``): every profile is scored
on dependency names alone, exactly as before. The ``claude-plugin`` profile declares the key, is a candidate only
when the signature carries it, and wins a tie within the same source over a profile that declares none; a project
or user profile still wins a tie by source. So the signal never moves an existing match, it only picks the plugin
profile where the generic Python profile would have matched with the same score.
Only for a Python repository (the repository ROOT is Python: ``primary_language`` is ``python``, i.e. a pyproject and
no JavaScript dependencies in the root package.json): the promoted profile carries Python commands, CI and CodeQL,
so a markdown-only, TypeScript or mixed plugin keeps the match it had (typically ``generic``).
The key also appears in the snapshot's ``stack.runtime`` (additive; hidden from rendered runtime lists).
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

    if stack.get("primary_language") != "python":  # the profile it promotes is a Python toolchain: only a Python repo
        return stack
    dirs = [project_root / ".claude-plugin", *sorted(project_root.glob("plugins/*/.claude-plugin"))]
    if any(d.is_dir() and not excluded(d) for d in dirs):
        stack.setdefault("runtime", {})[RUNTIME_KEY] = ".claude-plugin/"
        signals = stack.setdefault("signals", [])
        if SIGNAL not in signals:
            signals.append(SIGNAL)
    return stack
