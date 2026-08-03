"""``main()``'s branches, driven IN-PROCESS so they are measurable.

The sibling modules run the real bootstrap as a **subprocess**, which is the
right proof that it composes: only a real process exercises the
``Path(__file__)`` walk that finds the cache from the hook's own location. But a
subprocess is invisible to coverage — a shell-out test measures 0% of the code
it exercises — so every branch in ``main()`` read as untested, and the changed-
line gate saw a 131-statement file at 56%.

This module closes that measurement gap without weakening the proof. ``main()``
resolves the cache from ``Path(__file__)`` looked up in MODULE GLOBALS at call
time, so pointing the loaded module's ``__file__`` at a hook inside a fake cache
tree drives the real function over the real fixtures, in-process. Coverage then
attributes to the canonical file rather than to a throwaway copy.

The subprocess tests stay authoritative for composition; these are for branch
reachability. Where they overlap, the subprocess assertion is the one to trust.
"""

from __future__ import annotations

import io
import sys
from collections import Counter
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling ensure_shared_cache_fixtures module

from ensure_shared_cache_fixtures import (  # noqa: E402
    OTHER_SRC,
    PLUGINS_SENTINEL,
    RUN_SENTINEL_SRC,
    SHARED_SENTINEL,
    cache_and_marketplace,
    hook_module,
    install,
    install_run,
    make_shared,
    mirror,
    mirror_all,
)


def _place(cache_sw: Path) -> Path:
    """The hook's own location inside the fake cache — an INSTALLED plugin file.

    Must exist before ``mirror_all``: shipwright-build is a plugin like any
    other, so a cache is not "whole" until its mirror exists too.
    """
    here = cache_sw / "shipwright-build" / "0.2.2" / "scripts" / "hooks" / "ensure_shared_cache.py"
    here.parent.mkdir(parents=True, exist_ok=True)
    here.touch(exist_ok=True)
    return here


def _drive(monkeypatch, cache_sw: Path, capsys, payload: str = "{}"):
    """Run the real ``main()`` as if invoked from a hook inside ``cache_sw``."""
    hook = hook_module()
    here = _place(cache_sw)
    monkeypatch.setattr(hook, "__file__", str(here))
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload))
    rc = hook.main()
    return rc, capsys.readouterr().err


def test_main_heals_both_trees_on_a_fresh_install(tmp_path, monkeypatch, capsys):
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    install_run(cache_sw)

    rc, err = _drive(monkeypatch, cache_sw, capsys)

    assert rc == 0
    assert (cache_sw / "shared" / SHARED_SENTINEL).is_file()
    assert (cache_sw / "plugins" / PLUGINS_SENTINEL).is_file()
    assert "shared" in err and "plugins" in err


def test_main_tops_up_a_partial_shared_from_our_own_clone(tmp_path, monkeypatch, capsys):
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    (mp_shared / "scripts" / "tools").mkdir(parents=True, exist_ok=True)
    (mp_shared / "scripts" / "tools" / "reaped.py").write_text("X = 1\n", encoding="utf-8")
    make_shared(cache_sw / "shared")            # sentinel alive, tools/ reaped
    install_run(cache_sw)
    mirror(cache_sw, "shipwright-run", RUN_SENTINEL_SRC)

    rc, err = _drive(monkeypatch, cache_sw, capsys)

    assert rc == 0
    assert (cache_sw / "shared" / "scripts" / "tools" / "reaped.py").is_file()
    assert "self-healed" in err


def test_main_is_a_silent_noop_on_a_whole_cache(tmp_path, monkeypatch, capsys):
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")
    install_run(cache_sw)
    install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    _place(cache_sw)                 # the hook's own plugin is a plugin too
    mirror_all(cache_sw)

    rc, err = _drive(monkeypatch, cache_sw, capsys)

    assert rc == 0
    assert "self-healed" not in err
    assert "update-marketplace" not in err


def test_healthy_coordinated_main_walks_each_tree_once(
    tmp_path, monkeypatch, capsys,
):
    hook = hook_module()
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")
    install_run(cache_sw)
    _place(cache_sw)
    mirror_all(cache_sw)
    seen: list[Path] = []
    real_delivered = hook._delivered

    def measured(root: Path):
        seen.append(root)
        return real_delivered(root)

    monkeypatch.setattr(hook, "_delivered", measured)
    rc, err = _drive(
        monkeypatch, cache_sw, capsys, '{"session_id":"healthy-scan"}',
    )

    assert rc == 0 and "self-healed" not in err
    assert seen and max(Counter(seen).values()) == 1


def test_main_advises_when_shared_cannot_be_restored(tmp_path, monkeypatch, capsys):
    """No clone anywhere: plugins/ still heals, shared/ gets the actionable note."""
    cache_sw, _mp = cache_and_marketplace(tmp_path)   # marketplaces/ never created
    install_run(cache_sw)

    rc, err = _drive(monkeypatch, cache_sw, capsys)

    assert rc == 0
    assert (cache_sw / "plugins" / PLUGINS_SENTINEL).is_file(), "plugins/ heals with no clone"
    assert not (cache_sw / "shared").exists()
    assert "update-marketplace.sh" in err


def test_main_withholds_completion_when_shared_has_no_authoritative_source(
    tmp_path, monkeypatch, capsys,
):
    cache_sw, _mp = cache_and_marketplace(tmp_path)
    make_shared(cache_sw / "shared")
    install_run(cache_sw)
    _place(cache_sw)
    mirror_all(cache_sw)

    rc, err = _drive(
        monkeypatch, cache_sw, capsys, '{"session_id":"unverified-shared"}',
    )

    claims = cache_sw / ".sessionstart-claims"
    assert rc == 0
    assert not list(claims.glob("*.done"))
    assert "completion not published" in err


def test_main_restores_shared_from_a_foreign_clone_by_scanning(tmp_path, monkeypatch, capsys):
    """The broad fallback repairs from another clone but cannot publish readiness."""
    cache_sw, _mp = cache_and_marketplace(tmp_path)
    foreign = tmp_path / ".claude" / "plugins" / "marketplaces" / "someone-else" / "shared"
    make_shared(foreign)
    install_run(cache_sw)

    rc, err = _drive(
        monkeypatch, cache_sw, capsys, '{"session_id":"foreign-restore"}',
    )

    assert rc == 0
    assert (cache_sw / "shared" / SHARED_SENTINEL).is_file()
    assert not list((cache_sw / ".sessionstart-claims").glob("*.done"))
    assert "completion not published" in err


def test_main_is_fail_open_when_everything_below_it_raises(tmp_path, monkeypatch, capsys):
    """The outer guard: a session is never blocked, whatever went wrong."""
    hook = hook_module()
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    install_run(cache_sw)

    def boom(*_a, **_k):
        raise RuntimeError("simulated non-OSError fault")

    monkeypatch.setattr(hook, "_shared_healthy", boom)

    rc, err = _drive(monkeypatch, cache_sw, capsys)

    assert rc == 0, "fail-open: the hook must never block a session"
    assert "skipped" in err and "simulated non-OSError fault" in err


def test_main_never_publishes_completion_after_copy_failure(
    tmp_path, monkeypatch, capsys,
):
    hook = hook_module()
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    install_run(cache_sw)

    def fail_copy(*_args, **_kwargs):
        raise OSError("transient copy failure")

    monkeypatch.setattr(hook.shutil, "copytree", fail_copy)
    rc, err = _drive(
        monkeypatch, cache_sw, capsys, '{"session_id":"copy-failure"}',
    )

    claims = cache_sw / hook._CLAIM_DIRNAME
    assert rc == 0
    assert list(claims.glob("*.claim"))
    assert not list(claims.glob("*.done"))
    assert "completion not published" in err


@pytest.mark.parametrize("unreadable", ["cache-root", "installed-plugin"])
def test_main_never_publishes_completion_after_plugin_enumeration_failure(
    tmp_path, monkeypatch, capsys, unreadable,
):
    hook = hook_module()
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")
    install_run(cache_sw)
    _place(cache_sw)
    mirror_all(cache_sw)
    denied = cache_sw if unreadable == "cache-root" else cache_sw / "shipwright-run"
    real_iterdir = Path.iterdir

    def guarded_iterdir(path: Path):
        if path == denied:
            raise PermissionError("enumeration denied")
        return real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", guarded_iterdir)
    rc, err = _drive(
        monkeypatch, cache_sw, capsys,
        f'{{"session_id":"enumeration-{unreadable}"}}',
    )

    claims = cache_sw / hook._CLAIM_DIRNAME
    assert rc == 0
    assert not list(claims.glob("*.done"))
    assert "completion not published" in err


def test_main_never_repairs_without_global_writer_lease(
    tmp_path, monkeypatch, capsys,
):
    hook = hook_module()
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    install_run(cache_sw)
    monkeypatch.setattr(hook, "acquire_cache_lock", lambda _path: None)
    rc, err = _drive(
        monkeypatch, cache_sw, capsys, '{"session_id":"lock-failure"}',
    )

    assert rc == 0
    assert not (cache_sw / "shared").exists()
    assert not (cache_sw / "plugins").exists()
    assert "writer lock unavailable" in err


def test_main_is_a_noop_in_the_dev_plugin_dir_model(tmp_path, monkeypatch, capsys):
    """repo/plugins/<plugin>/scripts/hooks/<f>: both dirs are the real repo."""
    hook = hook_module()
    repo = tmp_path / "repo"
    make_shared(repo / "shared")
    sentinel = repo / "plugins" / PLUGINS_SENTINEL
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.write_text("x\n", encoding="utf-8")
    here = repo / "plugins" / "shipwright-build" / "scripts" / "hooks" / "ensure_shared_cache.py"
    here.parent.mkdir(parents=True, exist_ok=True)
    here.touch()
    monkeypatch.setattr(hook, "__file__", str(here))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

    rc = hook.main()
    err = capsys.readouterr().err

    assert rc == 0
    assert "self-healed" not in err


def test_main_survives_stdin_that_is_not_json(tmp_path, monkeypatch, capsys):
    """Hook protocol: consume stdin, never fail on it."""
    hook = hook_module()
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    make_shared(cache_sw / "shared")
    install_run(cache_sw)
    here = _place(cache_sw)
    mirror_all(cache_sw)
    monkeypatch.setattr(hook, "__file__", str(here))
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json at all"))

    assert hook.main() == 0
