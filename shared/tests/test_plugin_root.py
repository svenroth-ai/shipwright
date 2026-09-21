"""Tests for shared/scripts/lib/plugin_root.py (M2 — one plugin-root contract).

Covers the resolution precedence (SHIPWRIGHT_PLUGIN_ROOT > CLAUDE_PLUGIN_ROOT >
PLUGIN_ROOT > error) and the three real on-disk cache shapes the
resolver must treat identically: the monorepo working tree, a Claude
plugin-cache install, and a Codex plugin-cache install (shape confirmed live
against a real Codex CLI during Repo Scout —
``.shipwright/planning/iterate/2026-09-20-codex-plugin-bundle-root-contract.md``).
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in ("SHIPWRIGHT_PLUGIN_ROOT", "PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT"):
        monkeypatch.delenv(var, raising=False)


def test_shipwright_plugin_root_wins_outright(monkeypatch, tmp_path):
    monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(tmp_path))
    monkeypatch.setenv("PLUGIN_ROOT", str(tmp_path / "other"))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path / "other2"))

    from lib.plugin_root import resolve_plugin_root
    assert resolve_plugin_root() == tmp_path


def test_codex_native_plugin_root_used_when_shipwright_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("PLUGIN_ROOT", str(tmp_path))

    from lib.plugin_root import resolve_plugin_root
    assert resolve_plugin_root() == tmp_path


def test_claude_plugin_root_compat_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))

    from lib.plugin_root import resolve_plugin_root
    assert resolve_plugin_root() == tmp_path


def test_claude_compat_wins_over_bare_plugin_root(monkeypatch, tmp_path):
    """CLAUDE_PLUGIN_ROOT outranks bare PLUGIN_ROOT (doubt-review,
    2026-09-20): Codex sets both to the SAME value for a plugin-bundled
    hook, so their relative order carries no Codex-side information, while
    PLUGIN_ROOT is a generic enough name that an unrelated ambient tool
    could set it under a plain Claude session — CLAUDE_PLUGIN_ROOT is always
    the one Claude itself sets per hook invocation, so it must not be
    outranked by a name Shipwright does not control."""
    claude_compat = tmp_path / "claude-compat"
    ambient_stray = tmp_path / "ambient-stray"
    monkeypatch.setenv("PLUGIN_ROOT", str(ambient_stray))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(claude_compat))

    from lib.plugin_root import resolve_plugin_root
    assert resolve_plugin_root() == claude_compat


def test_none_set_raises_clear_error(monkeypatch):
    from lib.plugin_root import PluginRootUnresolvedError, resolve_plugin_root
    with pytest.raises(PluginRootUnresolvedError):
        resolve_plugin_root()


@pytest.mark.covers("FR-01.21/AC02")
@pytest.mark.parametrize(
    "env_var,layout_factory",
    [
        (
            "CLAUDE_PLUGIN_ROOT",
            lambda tmp_path: tmp_path
            / "cache" / "shipwright" / "shipwright-iterate" / "0.4.1",
        ),
        (
            "PLUGIN_ROOT",
            # The REAL live-confirmed Codex install shape (doubt-review,
            # 2026-09-20): the bundle is ONE umbrella plugin, installed as
            # `codex plugin add shipwright@shipwright`, so both the
            # marketplace AND plugin path segments are literally
            # "shipwright" — never a per-plugin name like
            # "shipwright-iterate". This resolver returns the raw value
            # regardless of shape (it does not parse path components), but
            # the fixture itself must match reality, not a shape the real
            # bundle never produces — see docstring below and this iterate's
            # Confidence Calibration for what this test does and does NOT
            # prove.
            lambda tmp_path: tmp_path
            / "plugins" / "cache" / "shipwright" / "shipwright" / "0.33.1",
        ),
    ],
)
def test_resolves_identically_under_claude_and_codex_cache_shapes(
    monkeypatch, tmp_path, env_var, layout_factory
):
    """AC2: ``resolve_plugin_root()`` returns the raw env-var value verbatim
    regardless of which variable or which real on-disk shape produced it —
    it deliberately does not parse or guess cache topology (M2). This proves
    ONLY the resolver's own value-level contract, not that anything
    downstream which DOES parse the path (e.g. `phase_from_plugin_root()`'s
    ``shipwright-<phase>`` name matching) recognizes the real Codex umbrella
    install shape — it does not, since that shape has no per-plugin name
    component; phase-aware hook behavior under the Codex bundle is a
    separate, unsolved concern for a later milestone (doubt-review,
    2026-09-20)."""
    plugin_root = layout_factory(tmp_path)
    plugin_root.mkdir(parents=True)
    monkeypatch.setenv(env_var, str(plugin_root))

    from lib.plugin_root import resolve_plugin_root
    assert resolve_plugin_root() == plugin_root


def test_monorepo_working_tree_shape_via_shipwright_plugin_root(monkeypatch, tmp_path):
    """The monorepo shape has no CLAUDE_PLUGIN_ROOT/PLUGIN_ROOT at all — a
    caller running scripts directly from the working tree sets
    SHIPWRIGHT_PLUGIN_ROOT itself (or a script derives it from __file__ and
    never calls the resolver). This pins that the resolver still returns
    exactly what was given, with no cache-topology guessing."""
    plugin_root = tmp_path / "plugins" / "shipwright-iterate"
    plugin_root.mkdir(parents=True)
    monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(plugin_root))

    from lib.plugin_root import resolve_plugin_root
    assert resolve_plugin_root() == plugin_root


def test_returns_path_not_string(monkeypatch, tmp_path):
    monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(tmp_path))

    from lib.plugin_root import resolve_plugin_root
    assert isinstance(resolve_plugin_root(), Path)


def test_resolve_plugin_root_str_preserves_exact_separator_style(monkeypatch):
    """A caller that only re-emits the value (capture_session_id.py's
    SessionStart injection) must not have its separator style silently
    rewritten by a Path round-trip — this is what makes AC3's regression
    bar ('existing Claude-driven flows unaffected') hold exactly, not just
    approximately."""
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", "/fake/plugin/root")

    from lib.plugin_root import resolve_plugin_root_str
    assert resolve_plugin_root_str() == "/fake/plugin/root"
