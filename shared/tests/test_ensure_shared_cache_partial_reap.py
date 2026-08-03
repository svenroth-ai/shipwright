"""The surviving-sentinel partial reap — the case the bootstrap exists for.

A reap removes files from a tree that already exists. Every sentinel that
survives it therefore reports "healthy", which is why until 2026-08-01 the
self-heal hook repaired a *missing* tree and never a *damaged* one:

- ``_shared_healthy`` judged 1013 files from ``scripts/lib/project_root.py``;
- ``_plugins_healthy`` judged all fourteen mirrors from shipwright-run's
  ``phase_task_lifecycle.py``.

ADR-120 measured the first: a reap of the 55 ``shared/scripts/tools/verifiers/``
modules that every iterate's F11 imports left the sentinel standing, the heal
never fired, and F11 died with ``ModuleNotFoundError``.

Companion to ``test_ensure_shared_cache_integration`` (fresh-install delivery);
layout builders come from ``ensure_shared_cache_fixtures``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling ensure_shared_cache_fixtures module

from ensure_shared_cache_fixtures import (  # noqa: E402
    OTHER_SRC,
    RUN_SENTINEL_SRC,
    cache_and_marketplace,
    install,
    install_run,
    make_shared,
    mirror,
    mirror_all,
    place_hook,
    run,
)


def test_heals_partial_plugin_mirror_behind_surviving_sentinel(tmp_path: Path):
    """A partial mirror of a NON-sentinel plugin is repaired.

    With shipwright-run's one file intact and ``shared/`` healthy, ``main()``
    used to return 0 before ``_heal_plugins`` ran, so a half-reaped
    shipwright-compliance mirror stayed broken forever.
    """
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")                    # shared/ fully healthy
    install_run(cache_sw)
    mirror(cache_sw, "shipwright-run", RUN_SENTINEL_SRC)     # sentinel SURVIVES
    install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    mirror(cache_sw, "shipwright-compliance",                # ...but this one is partial
           {"scripts/lib/keep.py": OTHER_SRC["scripts/lib/keep.py"]})
    script = place_hook(cache_sw)

    result = run(script)

    assert result.returncode == 0, result.stderr
    repaired = cache_sw / "plugins" / "shipwright-compliance"
    assert (repaired / "scripts" / "lib" / "reaped.py").is_file(), (
        "a partially reaped mirror was not repaired — the health check still "
        "judges fourteen mirrors from one sentinel file"
    )
    assert (repaired / "skills" / "compliance" / "SKILL.md").is_file()
    assert "self-healed" in result.stderr


def test_heals_partial_shared_tree_behind_surviving_sentinel(tmp_path: Path):
    """A partial ``shared/`` is repaired while its sentinel is intact (ADR-120)."""
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    verifier = mp_shared / "scripts" / "tools" / "verifiers" / "integration_coverage.py"
    verifier.parent.mkdir(parents=True, exist_ok=True)
    verifier.write_text("def check():\n    return True\n", encoding="utf-8")
    make_shared(cache_sw / "shared")                    # sentinel present, verifiers REAPED
    install_run(cache_sw)
    script = place_hook(cache_sw)
    mirror_all(cache_sw)                                # plugins side deliberately whole

    result = run(script)

    assert result.returncode == 0, result.stderr
    healed = cache_sw / "shared" / "scripts" / "tools" / "verifiers" / "integration_coverage.py"
    assert healed.is_file(), (
        "a partially reaped shared/ was not repaired — one sentinel still stands "
        "for the whole tree (ADR-120's unrecovered case)"
    )


def test_neither_short_circuit_survives(tmp_path: Path):
    """Both trees partial, both sentinels alive — both must still be repaired.

    Pins the two independent routes that skipped the repair: the combined early
    return, and the ``not _plugins_healthy(...) and _heal_plugins(...)``
    short-circuit that made the second operand unreachable.
    """
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    (mp_shared / "scripts" / "tools").mkdir(parents=True, exist_ok=True)
    (mp_shared / "scripts" / "tools" / "gone.py").write_text("X = 1\n", encoding="utf-8")
    make_shared(cache_sw / "shared")                         # shared partial, sentinel alive
    install_run(cache_sw)
    mirror(cache_sw, "shipwright-run", RUN_SENTINEL_SRC)     # plugins sentinel alive
    install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    mirror(cache_sw, "shipwright-compliance",                # ...mirror partial
           {"scripts/lib/keep.py": OTHER_SRC["scripts/lib/keep.py"]})
    script = place_hook(cache_sw)

    result = run(script)

    assert result.returncode == 0, result.stderr
    assert (cache_sw / "shared" / "scripts" / "tools" / "gone.py").is_file(), (
        "shared/ not repaired — a surviving plugins sentinel still suppresses it"
    )
    assert (cache_sw / "plugins" / "shipwright-compliance" / "scripts" / "lib"
            / "reaped.py").is_file(), (
        "plugins/ not repaired — a surviving shared sentinel still suppresses it"
    )


def test_a_foreign_marketplace_clone_never_decides_completeness(tmp_path: Path):
    """Only OUR OWN clone may judge whether the cached shared/ is whole.

    The restore path deliberately accepts any marketplace clone carrying the
    sentinel — when ``shared/`` is absent, a stranger's copy beats nothing. Reusing
    that broad search to answer "is ours COMPLETE?" would report the stranger's
    extra files as our gaps and copy their code into this cache on every session.
    """
    cache_sw, _mp = cache_and_marketplace(tmp_path)   # marketplaces/shipwright NOT created
    foreign = tmp_path / ".claude" / "plugins" / "marketplaces" / "someone-else" / "shared"
    make_shared(foreign)
    (foreign / "scripts" / "tools").mkdir(parents=True, exist_ok=True)
    (foreign / "scripts" / "tools" / "not_ours.py").write_text("X = 1\n", encoding="utf-8")
    make_shared(cache_sw / "shared")                  # ours is present and healthy
    install_run(cache_sw)
    script = place_hook(cache_sw)
    mirror_all(cache_sw)

    result = run(script)

    assert result.returncode == 0, result.stderr
    assert not (cache_sw / "shared" / "scripts" / "tools" / "not_ours.py").exists(), (
        "a foreign marketplace's shared/ was treated as the authority on ours"
    )
    assert "self-healed" not in result.stderr


def test_a_foreign_marketplace_clone_still_restores_an_absent_shared(tmp_path: Path):
    """...but the broad restore path is preserved: something beats nothing."""
    cache_sw, _mp = cache_and_marketplace(tmp_path)
    foreign = tmp_path / ".claude" / "plugins" / "marketplaces" / "someone-else" / "shared"
    make_shared(foreign)
    install_run(cache_sw)
    script = place_hook(cache_sw)

    result = run(script)

    assert result.returncode == 0, result.stderr
    assert (cache_sw / "shared" / "scripts" / "lib" / "project_root.py").is_file(), (
        "an absent shared/ must still be restored from whatever clone exists"
    )


def test_noop_when_cache_manager_markers_are_present(tmp_path: Path):
    """A whole cache stays a no-op even though the cache manager litters it.

    ``.in_use/<pid>`` (volatile per-PID refcounts) lives in the installed plugin
    dirs but NOT in the mirrors, and ``.orphaned_at`` the reverse. Measured on
    the live cache 2026-08-01: counting either one makes all fourteen mirrors
    look incomplete forever, which would turn this hook from a no-op into a
    1464-file copy on EVERY session start.
    """
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")
    src = install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    install_run(cache_sw)
    script = place_hook(cache_sw)
    mirror_all(cache_sw)                                     # everything genuinely whole

    # cache-manager litter, exactly as observed live
    (src / ".in_use").mkdir(parents=True, exist_ok=True)
    (src / ".in_use" / "8408").write_text('{"pid":8408}', encoding="utf-8")
    (cache_sw / "plugins" / "shipwright-compliance" / ".orphaned_at").write_text(
        "x", encoding="utf-8")
    (cache_sw / "shared" / "scripts" / ".orphaned_at").write_text("x", encoding="utf-8")

    result = run(script)

    assert result.returncode == 0, result.stderr
    assert "self-healed" not in result.stderr, (
        "cache-manager marker files were counted as deliverable content — this "
        "re-copies the whole cache on every session start"
    )
    assert not (cache_sw / "plugins" / "shipwright-compliance" / ".in_use").exists(), (
        "a volatile per-PID refcount was mirrored into the cross-plugin tree"
    )
