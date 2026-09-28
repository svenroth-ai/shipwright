"""Reverse-direction drift protection for the vendored ``ensure_shared_cache``
SessionStart hook — split out of ``test_ensure_shared_cache_vendored.py``
(same-directory sibling, iterate-2026-09-28-hooks-uv-run-project-pin) to
stay under the repo's 300-LOC guideline for test files. The small set of
path constants/helpers below are duplicated from that file rather than
imported — this pytest root has no package `__init__.py`/sys.path wiring
for cross-test-file imports between plain test modules.

See that module's docstring for the full forward/reverse drift-protection
design. This file covers only the reverse direction: every vendored copy
found on disk belongs to a hook-bearing plugin (no orphan copy) and matches
its canonical source.
"""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_CANONICAL = _REPO / "shared" / "templates" / "hooks" / "ensure_shared_cache.py"
_LOCK_CANONICAL = _CANONICAL.with_name("cache_repair_lock.py")
_GUARD_CANONICAL = _CANONICAL.with_name("run_if_cache_ready.py")


def _norm(b: bytes) -> bytes:
    return b.replace(b"\r\n", b"\n")


def _hook_bearing_plugins() -> list[Path]:
    """Every plugin whose hooks.json references the ``../../shared`` delivery."""
    out = []
    for hj in sorted((_REPO / "plugins").glob("*/hooks/hooks.json")):
        if "../../shared" in hj.read_text(encoding="utf-8"):
            out.append(hj.parent.parent)  # .../plugins/<plugin>
    return out


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

    lock_canon = _norm(_LOCK_CANONICAL.read_bytes())
    for copy in sorted((_REPO / "plugins").glob("*/scripts/hooks/cache_repair_lock.py")):
        plugin_name = copy.parents[2].name
        assert plugin_name in hb, f"orphan cache_repair_lock copy in {plugin_name}"
        assert _norm(copy.read_bytes()) == lock_canon, (
            f"{plugin_name} cache_repair_lock copy drifted"
        )

    guard_canon = _norm(_GUARD_CANONICAL.read_bytes())
    for copy in sorted((_REPO / "plugins").glob("*/scripts/hooks/run_if_cache_ready.py")):
        plugin_name = copy.parents[2].name
        assert plugin_name in hb, f"orphan run_if_cache_ready copy in {plugin_name}"
        assert _norm(copy.read_bytes()) == guard_canon, (
            f"{plugin_name} run_if_cache_ready copy drifted"
        )
