"""Drift protection for the vendored ``ensure_shared_cache`` SessionStart hook.

The self-heal bootstrap cannot live in ``shared/`` and be imported at runtime —
it exists precisely to repair a missing ``shared/``. So the canonical source at
``shared/templates/hooks/ensure_shared_cache.py`` is **vendored byte-identically**
into every hook-bearing plugin's ``scripts/hooks/``. This is the only delivery a
plain ``claude plugin install`` guarantees (a plugin-local file), so it is load-
bearing that the copies never drift and are actually wired into SessionStart.

Bidirectional drift protection (the Registry-driven-SSoT rule):
  - forward  — every hook-bearing plugin (any ``hooks.json`` referencing
    ``../../shared``) carries a copy identical to the canonical AND registers it
    as the FIRST SessionStart hook;
  - reverse  — every ``plugins/*/scripts/hooks/ensure_shared_cache.py`` on disk
    belongs to a hook-bearing plugin (no orphan copy) and matches the canonical.

Comparison is EOL-normalised: the gate is on content, not on a platform's / git
config's line-ending convention.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO / "shared" / "templates" / "hooks" / "ensure_shared_cache.py"
_VENDOR_REL = ("scripts", "hooks", "ensure_shared_cache.py")


def _norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def _hook_bearing_plugins() -> list[Path]:
    """Every plugin whose hooks.json references the ``../../shared`` delivery."""
    out = []
    for hj in sorted((_REPO / "plugins").glob("*/hooks/hooks.json")):
        if "../../shared" in hj.read_text(encoding="utf-8"):
            out.append(hj.parent.parent)  # .../plugins/<plugin>
    return out


def test_canonical_source_exists():
    assert _CANONICAL.is_file(), f"canonical bootstrap missing at {_CANONICAL}"
    text = _CANONICAL.read_text(encoding="utf-8")
    assert "self-heal" in text.lower()
    assert len(text.splitlines()) > 20


def test_hook_bearing_set_is_discovered():
    # Sanity: the discovery must actually find plugins, else the gate no-ops.
    assert len(_hook_bearing_plugins()) >= 10


def test_forward_every_hook_bearing_plugin_has_identical_copy():
    canon = _norm(_CANONICAL.read_bytes())
    missing, drifted = [], []
    for plugin in _hook_bearing_plugins():
        copy = plugin.joinpath(*_VENDOR_REL)
        if not copy.is_file():
            missing.append(plugin.name)
        elif _norm(copy.read_bytes()) != canon:
            drifted.append(plugin.name)
    assert not missing, (
        "hook-bearing plugins missing the vendored ensure_shared_cache bootstrap: "
        f"{missing} — copy shared/templates/hooks/ensure_shared_cache.py into each "
        "plugin's scripts/hooks/"
    )
    assert not drifted, (
        f"vendored ensure_shared_cache drifted from the canonical: {drifted} — "
        "re-vendor shared/templates/hooks/ensure_shared_cache.py to all copies"
    )


def test_forward_registered_as_first_session_start_hook():
    offenders = []
    for plugin in _hook_bearing_plugins():
        data = json.loads((plugin / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        try:
            first = data["hooks"]["SessionStart"][0]["hooks"][0]["command"]
        except (KeyError, IndexError, TypeError):
            first = ""
        if not ("ensure_shared_cache.py" in first
                and "${CLAUDE_PLUGIN_ROOT}/scripts/hooks/" in first):
            offenders.append(plugin.name)
    assert not offenders, (
        "these hook-bearing plugins do not invoke ensure_shared_cache as their "
        f"FIRST SessionStart hook: {offenders} — it must run before any "
        "../../shared/* hook so the self-heal happens first"
    )


def test_reverse_no_orphan_vendored_copies():
    hb = {p.name for p in _hook_bearing_plugins()}
    canon = _norm(_CANONICAL.read_bytes())
    for copy in sorted((_REPO / "plugins").glob("*/scripts/hooks/ensure_shared_cache.py")):
        plugin_name = copy.parents[2].name  # scripts/hooks/<f> -> plugin dir
        assert plugin_name in hb, (
            f"orphan ensure_shared_cache copy in non-hook-bearing plugin "
            f"{plugin_name!r} — either wire that plugin's ../../shared hooks or "
            "remove the stray copy"
        )
        assert _norm(copy.read_bytes()) == canon, f"{plugin_name} copy drifted"
