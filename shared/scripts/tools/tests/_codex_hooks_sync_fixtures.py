"""Shared fixtures for the codex_hooks_sync.py test files (R1b). Split out
so neither test file crosses the repo's 300-LOC guideline.
"""

from __future__ import annotations

import json
from pathlib import Path


def make_bundle(root: Path, hooks: dict) -> None:
    """*hooks* is the flat event map (``{<event>: [group, ...]}``). The
    on-disk shape is double-wrapped — ``plugin.json["hooks"]`` is
    ``build_hook_inventory``'s own ``{"hooks": {...}}`` return value,
    assigned verbatim by ``build_codex_plugin.py`` — so this fixture
    reproduces that real shape rather than the flat one, to actually catch
    a regression to the flat assumption (found live against a real built
    bundle during this run's own build)."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "BUILD_MANIFEST.json").write_text(
        json.dumps({"version": "0.0.0-test", "files": {"plugin.json": "0" * 64}}),
        encoding="utf-8",
    )
    codex_plugin_dir = root / ".codex-plugin"
    codex_plugin_dir.mkdir(parents=True, exist_ok=True)
    (codex_plugin_dir / "plugin.json").write_text(
        json.dumps({"hooks": {"hooks": hooks}}), encoding="utf-8"
    )


SAMPLE_HOOKS = {
    "SessionStart": [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": 'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on_start.py"',
                }
            ]
        }
    ],
    "Stop": [
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": 'uv run "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/on_stop.py"',
                }
            ],
        }
    ],
}
