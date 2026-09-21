"""Integration: the real Codex bundle's shape composes with the migrated
cleanup hook's resolver (M1+M2, campaign codex-plugin-execution-reliability).

`build_codex_plugin.build_bundle` and
`cleanup-review-scratch-on-code-reviewer-failure.py`'s `resolve_shared_root()`
were built and unit-tested independently — the builder against small fixture
trees, the hook against a hand-constructed directory shape. Nothing proved
the two actually AGREE on where `shared/` lives inside a real bundle. An
external code review already found once that the two disagreed (the hook
tried only the Claude-cache shape, `<root>/../../shared`, which points
outside a real bundle entirely) — see this iterate's ADR. This test drives
the REAL builder against the REAL 14-plugin monorepo tree (not a synthetic
fixture) and the REAL hook module, so a future change to either side that
silently reintroduces the mismatch fails here rather than only in
production under a live Codex install.

This is the cross_component integration-coverage row for
iterate-2026-09-20-codex-plugin-bundle-root-contract. Lives in
integration-tests/ (a CI-run root) rather than shared/tests/, per ADR-044.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _REPO_ROOT / "shared" / "scripts" / "tools"
_HOOK_PATH = (
    _REPO_ROOT / "plugins" / "shipwright-build" / "scripts" / "hooks"
    / "cleanup-review-scratch-on-code-reviewer-failure.py"
)


def _load_hook():
    spec = importlib.util.spec_from_file_location(
        "cleanup_review_scratch_on_code_reviewer_failure_it", _HOOK_PATH,
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_migrated_hook_finds_shared_inside_a_real_built_bundle(tmp_path, monkeypatch):
    if str(_TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(_TOOLS_DIR))
    from build_codex_plugin import build_bundle  # noqa: PLC0415

    out_dir = tmp_path / "dist" / "codex-plugin"
    result = build_bundle(project_root=_REPO_ROOT, out_dir=out_dir)
    assert result.skill_count > 0
    assert (out_dir / "shared").is_dir(), "builder did not emit the bundle-shape shared/ sibling"

    hook = _load_hook()
    monkeypatch.delenv("SHIPWRIGHT_PLUGIN_ROOT", raising=False)
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(out_dir))
    monkeypatch.delenv("PLUGIN_ROOT", raising=False)

    resolved = hook.resolve_shared_root()

    assert resolved == out_dir / "shared"
    assert (resolved / "scripts" / "lib" / "plugin_root.py").is_file(), (
        "resolved shared/ does not contain the real shared tree the builder copied"
    )
