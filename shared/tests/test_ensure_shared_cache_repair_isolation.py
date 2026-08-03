"""What happens when a repair CANNOT proceed — and what must still happen anyway.

A completeness check reaches states the old `dst.exists()` skip made
unreachable: it now tries to copy into trees that may be wedged, owned by
another tool, or unwritable. Three properties matter, and none of them is
visible from a happy-path test:

- a wedged mirror must not take the other thirteen down with it;
- a failed ``shared/`` copy must not skip the ``plugins/`` repair below it;
- a mirror the POSIX syncer owns as a SYMLINK must never be written through —
  a stale link points at an OLDER installed version directory, so copying
  through it corrupts a tree this hook does not own, and self-conceals (the
  next run reads the mirror as complete).

Wedging is done with a directory standing where a file must be written, which
makes ``copytree`` raise without permission games or platform tricks.

Companion to ``test_ensure_shared_cache_partial_reap`` (the surviving-sentinel
cases); layout builders come from ``ensure_shared_cache_fixtures``.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling ensure_shared_cache_fixtures module

from ensure_shared_cache_fixtures import (  # noqa: E402
    OTHER_SRC,
    RUN_SENTINEL_SRC,
    cache_and_marketplace,
    hook_module,
    install,
    install_run,
    make_shared,
    mirror,
    place_hook,
    run,
)


def test_one_unwritable_mirror_does_not_block_the_others(tmp_path: Path):
    """A per-mirror copy failure is isolated.

    The healer copies fourteen mirrors in one loop. Before the ``try`` moved
    inside it, the first ``OSError`` aborted the whole run — so one wedged plugin
    took the other thirteen down with it.
    """
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")
    install_run(cache_sw)

    # wedged: a directory sits where scripts/lib/keep.py must be written
    install(cache_sw, "shipwright-adopt", "0.2.1", OTHER_SRC)
    wedged = cache_sw / "plugins" / "shipwright-adopt" / "scripts" / "lib" / "keep.py"
    wedged.mkdir(parents=True)
    (wedged / "inner").write_text("x", encoding="utf-8")

    # ordinary: merely partial, and sorts AFTER the wedged one
    install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    mirror(cache_sw, "shipwright-compliance",
           {"scripts/lib/keep.py": OTHER_SRC["scripts/lib/keep.py"]})
    script = place_hook(cache_sw)

    result = run(script)

    assert result.returncode == 0, result.stderr
    assert (cache_sw / "plugins" / "shipwright-compliance" / "scripts" / "lib"
            / "reaped.py").is_file(), (
        "a wedged mirror aborted the loop and starved the plugins after it"
    )


def test_a_failed_shared_copy_does_not_skip_the_plugins_repair(tmp_path: Path):
    """The two trees are repaired independently.

    ``shared/`` is attempted first; if its copy raised uncaught, the plugins
    repair below it never ran and the session was left with both trees broken
    instead of one.
    """
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    (mp_shared / "scripts" / "tools").mkdir(parents=True, exist_ok=True)
    (mp_shared / "scripts" / "tools" / "wanted.py").write_text("X = 1\n", encoding="utf-8")
    make_shared(cache_sw / "shared")
    # wedge the shared copy: a directory where track_tool_calls.py must land
    blocked = cache_sw / "shared" / "scripts" / "hooks" / "track_tool_calls.py"
    blocked.unlink()
    blocked.mkdir()
    (blocked / "inner").write_text("x", encoding="utf-8")

    install_run(cache_sw)
    install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    mirror(cache_sw, "shipwright-compliance",
           {"scripts/lib/keep.py": OTHER_SRC["scripts/lib/keep.py"]})
    script = place_hook(cache_sw)

    result = run(script)

    assert result.returncode == 0, result.stderr
    assert (cache_sw / "plugins" / "shipwright-compliance" / "scripts" / "lib"
            / "reaped.py").is_file(), (
        "a failed shared/ copy skipped the plugins/ repair entirely"
    )


def test_a_whole_cache_calls_copytree_ZERO_times(tmp_path: Path, monkeypatch):
    """AC3 asserted at the operation, not at the log line.

    The subprocess no-op test can only observe stderr, so an implementation that
    overlaid both healthy trees and merely suppressed the "self-healed" message
    would pass it while re-copying ~2500 files on every session start — the very
    regression this design is built to avoid. Count the copies instead.
    """
    hook = hook_module()
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")
    install_run(cache_sw)
    install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    mirror(cache_sw, "shipwright-run", RUN_SENTINEL_SRC)
    mirror(cache_sw, "shipwright-compliance", OTHER_SRC)

    # cache-manager litter, exactly as observed on the live cache
    (cache_sw / "shipwright-compliance" / "0.2.2" / ".in_use").mkdir(parents=True)
    (cache_sw / "shipwright-compliance" / "0.2.2" / ".in_use" / "8408").write_text(
        '{"pid":8408}', encoding="utf-8")
    (cache_sw / "plugins" / "shipwright-compliance" / ".orphaned_at").write_text(
        "x", encoding="utf-8")

    calls = []
    monkeypatch.setattr(hook.shutil, "copytree",
                        lambda *a, **k: calls.append(a[:2]))

    assert hook._heal_plugins(cache_sw, cache_sw / "plugins") is False
    assert calls == [], f"a whole cache was copied anyway: {calls}"


def test_heal_plugins_skips_a_mirror_that_is_a_symlink(tmp_path: Path, monkeypatch):
    """Cross-platform pin for the symlink guard.

    The end-to-end version below needs a REAL symlink and so runs only on POSIX
    (creating one on Windows needs a privilege ordinary sessions do not hold —
    verified, `OSError 1314`). This one drives the real ``_heal_plugins`` with
    ``is_symlink`` reporting True, so the guard is covered on every platform
    rather than only where CI happens to run.
    """
    hook = hook_module()
    cache_sw, _mp = cache_and_marketplace(tmp_path)
    install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    dst = cache_sw / "plugins" / "shipwright-compliance"
    dst.mkdir(parents=True)          # incomplete: nothing mirrored into it yet

    assert hook._heal_plugins(cache_sw, cache_sw / "plugins") is True, (
        "sanity: without the symlink guard this mirror is repaired"
    )

    shutil.rmtree(dst)
    dst.mkdir(parents=True)
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink",
                        lambda self: self == dst or real_is_symlink(self))

    readiness = []
    assert hook._heal_plugins(
        cache_sw, cache_sw / "plugins", readiness,
    ) is False, (
        "a mirror reported as a symlink was still copied into — the syncer owns "
        "it, and a stale link points at an OLDER installed version directory"
    )
    assert readiness == [False], "an unverified symlink mirror must not publish ready"
    assert not (dst / "scripts").exists(), "the healer wrote through the link"


@pytest.mark.skipif(
    os.name == "nt",
    reason="update-marketplace.sh only creates symlinked mirrors on POSIX; Windows "
           "gets real directories. Platform shape, not a missing capability — CI "
           "is Linux and runs this. The cross-platform guard pin is the unit test "
           "above.",
)
def test_a_symlinked_mirror_is_never_written_through(tmp_path: Path):
    """The mirror the POSIX syncer owns must be left alone.

    `update-marketplace.sh` links `cache/<name>/plugins/shipwright-X` at the
    installed version dir. If the link is STALE — a numerically newer version is
    installed while the link still points at the older one — a completeness check
    reports a gap and `copytree(dirs_exist_ok=True)` would follow the link and
    write the newer files into the OLDER installed version's directory.

    Unreachable before this change (`dst.exists()` is True for a symlink, so the
    loop always skipped), which is why no fixture modelled the layout.
    """
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")
    install_run(cache_sw)

    old = install(cache_sw, "shipwright-compliance", "0.2.0",
                  {"scripts/lib/keep.py": "OLD = 1\n"})
    install(cache_sw, "shipwright-compliance", "0.10.0", OTHER_SRC)   # newer, numerically
    link = cache_sw / "plugins" / "shipwright-compliance"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(old, target_is_directory=True)                    # STALE link
    script = place_hook(cache_sw)

    result = run(script)

    assert result.returncode == 0, result.stderr
    assert link.is_symlink(), "the mirror symlink was replaced by a real directory"
    assert not (old / "scripts" / "lib" / "reaped.py").exists(), (
        "the healer wrote through a stale mirror symlink into an OLDER installed "
        "version directory — a tree it does not own"
    )
    assert (old / "scripts" / "lib" / "keep.py").read_text(encoding="utf-8") == "OLD = 1\n", (
        "the older installed version's own file was overwritten"
    )
