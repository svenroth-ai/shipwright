"""Integration: the vendored ensure_shared_cache bootstrap heals a real layout.

The cross-component composition proof (the ``cross_component`` risk flag's
non-dodgeable integration coverage): stand up a faithful plugin-cache +
marketplace-clone tree, run the ACTUAL bootstrap as a subprocess exactly where a
hook would (so its ``Path(__file__)`` walk resolves against the fake tree), and
assert the compose for BOTH delivery gaps:

- ``shared/``  ← mirrored from the marketplace full-clone;
- ``plugins/`` ← mirrored from the installed versioned plugin dirs (no clone),
  so cross-plugin ``../../plugins/shipwright-X`` imports resolve.

This module covers **delivery** — the fresh-install and fail-open cases. The
*partial*-reap cases (a tree that exists but has lost files) live in
``test_ensure_shared_cache_partial_reap``; layout builders are shared via
``ensure_shared_cache_fixtures``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling ensure_shared_cache_fixtures module

from ensure_shared_cache_fixtures import (  # noqa: E402
    CANONICAL,
    PLUGINS_SENTINEL,
    SHARED_SENTINEL,
    cache_and_marketplace,
    install_run,
    make_shared,
    mirror_all,
    place_hook,
    run,
)


def test_heals_shared_and_plugins_on_fresh_install(tmp_path: Path):
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)           # marketplace clone carries shared/
    install_run(cache_sw)            # installed run = source for the plugins/ heal
    script = place_hook(cache_sw)
    assert not (cache_sw / "shared").exists() and not (cache_sw / "plugins").exists()

    result = run(script)

    assert result.returncode == 0, result.stderr
    assert (cache_sw / "shared" / SHARED_SENTINEL).is_file(), "shared/ not healed"
    assert (cache_sw / "plugins" / PLUGINS_SENTINEL).is_file(), "plugins/ not healed"
    assert not (cache_sw / "shared" / "__pycache__").exists(), "__pycache__ should be ignored"
    assert "shared" in result.stderr and "plugins" in result.stderr


def test_heals_plugins_without_marketplace_clone(tmp_path: Path):
    # No clone made -> shared cannot heal, but plugins/ heals from the installed dirs.
    cache_sw, _mp = cache_and_marketplace(tmp_path)
    install_run(cache_sw)
    script = place_hook(cache_sw)

    result = run(script)

    assert result.returncode == 0
    assert (cache_sw / "plugins" / PLUGINS_SENTINEL).is_file(), "plugins/ heals without a clone"
    assert not (cache_sw / "shared").exists(), "shared/ can't heal without a clone"
    assert "update-marketplace.sh" in result.stderr, "still guides about the missing shared/"


def test_idempotent_noop_when_both_present(tmp_path: Path):
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")                        # shared already healed
    install_run(cache_sw)
    script = place_hook(cache_sw)
    mirror_all(cache_sw)                                    # ...and so is every mirror

    result = run(script)

    assert result.returncode == 0
    assert (cache_sw / "plugins" / PLUGINS_SENTINEL).is_file()
    assert "self-healed" not in result.stderr  # fast-path no-op


def test_fail_open_when_no_clone_and_no_run(tmp_path: Path):
    cache_sw, _mp = cache_and_marketplace(tmp_path)  # no clone, no run installed
    script = place_hook(cache_sw)

    result = run(script)

    assert result.returncode == 0, "must never block a session (fail-open)"
    assert not (cache_sw / "shared").exists(), "shared/ cannot heal without a clone"
    assert "update-marketplace.sh" in result.stderr


def test_dev_plugin_dir_model_is_noop(tmp_path: Path):
    # --plugin-dir dev model: PLUGIN_ROOT = repo/plugins/<plugin>; repo/{shared,plugins}
    # are the real dirs -> both healthy -> no-op, never touches anything.
    repo = tmp_path / "repo"
    make_shared(repo / "shared")
    sentinel = repo / "plugins" / PLUGINS_SENTINEL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("x\n", encoding="utf-8")
    script = repo / "plugins" / "shipwright-build" / "scripts" / "hooks" / "ensure_shared_cache.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_bytes(CANONICAL.read_bytes())

    result = run(script)

    assert result.returncode == 0
    assert "self-healed" not in result.stderr
