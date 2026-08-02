"""The fail-open error paths, exercised IN-PROCESS.

Seven tests drive the hook's seven syntactic ``except OSError`` sites — the
guarantee that a SessionStart hook never blocks a session and never claims
health it cannot verify. The eighth separately covers the normal
``no usable clone`` return. Two error sites (the per-mirror and shared/ copy
guards) were already driven by subprocess isolation tests, and the mid-walk
``iterdir`` handler already had an in-process test; the remaining handlers were
not measured before this module.

The error sites matter more than their line count suggests: a handler that
returns a SHORT file set instead of ``None`` is exactly how this hook's original
false-healthy verdict comes back, one layer down.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling ensure_shared_cache_fixtures module

from ensure_shared_cache_fixtures import (  # noqa: E402
    OTHER_SRC,
    cache_and_marketplace,
    hook_module,
    install,
    install_run,
    make_shared,
    mirror,
)

_HOOK = hook_module()


def _tree(root: Path, rels: list[str]) -> Path:
    for rel in rels:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    return root


def test_delivered_is_none_when_an_entry_cannot_be_classified(tmp_path, monkeypatch):
    """`entry.is_dir()` raising must abandon the verdict, not skip the entry.

    Distinct from the iterdir failure: the directory listed fine, but one child
    could not be stat'd. Skipping it would silently under-count the source.
    """
    _tree(tmp_path, ["a.py", "b.py"])
    victim = (tmp_path / "b.py").resolve()
    real_is_dir = Path.is_dir

    def exploding_is_dir(self):
        if self.resolve() == victim:
            raise OSError(5, "simulated stat failure")
        return real_is_dir(self)

    monkeypatch.setattr(Path, "is_dir", exploding_is_dir)
    assert _HOOK._delivered(tmp_path) is None


def test_incomplete_is_none_when_the_DESTINATION_cannot_be_read(tmp_path, monkeypatch):
    """An unreadable destination is unknown too — never "complete"."""
    src = _tree(tmp_path / "src", ["a.py"])
    dst = _tree(tmp_path / "dst", ["a.py"])
    real_iterdir = Path.iterdir
    victim = dst.resolve()

    def exploding_iterdir(self):
        if self.resolve() == victim:
            raise OSError(5, "simulated I/O error")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", exploding_iterdir)
    assert _HOOK._incomplete(src, dst) is None


def test_find_marketplace_shared_is_none_when_no_clone_carries_the_sentinel(tmp_path):
    """`marketplaces/` exists but holds nothing usable — the scan finds nothing."""
    marketplaces = tmp_path / ".claude" / "plugins" / "marketplaces"
    (marketplaces / "someone-else" / "shared" / "scripts").mkdir(parents=True)
    cache_root = tmp_path / ".claude" / "plugins" / "cache" / "shipwright"
    cache_root.mkdir(parents=True)
    assert _HOOK._find_marketplace_shared(cache_root) is None


def test_find_marketplace_shared_survives_an_unreadable_marketplaces_dir(tmp_path, monkeypatch):
    marketplaces = tmp_path / ".claude" / "plugins" / "marketplaces"
    (marketplaces / "x").mkdir(parents=True)
    cache_root = tmp_path / ".claude" / "plugins" / "cache" / "shipwright"
    cache_root.mkdir(parents=True)
    real_iterdir = Path.iterdir
    victim = marketplaces.resolve()

    def exploding_iterdir(self):
        if self.resolve() == victim:
            raise OSError(13, "simulated permission denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", exploding_iterdir)
    assert _HOOK._find_marketplace_shared(cache_root) is None


def test_plugin_mirrors_yields_nothing_when_the_cache_root_is_unreadable(tmp_path, monkeypatch):
    cache_sw, _mp = cache_and_marketplace(tmp_path)
    install_run(cache_sw)
    real_iterdir = Path.iterdir
    victim = cache_sw.resolve()

    def exploding_iterdir(self):
        if self.resolve() == victim:
            raise OSError(13, "simulated permission denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", exploding_iterdir)
    assert list(_HOOK._plugin_mirrors(cache_sw, cache_sw / "plugins")) == []


def test_plugin_mirrors_skips_a_plugin_whose_versions_cannot_be_listed(tmp_path, monkeypatch):
    """One unreadable plugin dir must not starve the others."""
    cache_sw, _mp = cache_and_marketplace(tmp_path)
    install_run(cache_sw)
    bad = install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC).parent
    real_iterdir = Path.iterdir
    victim = bad.resolve()

    def exploding_iterdir(self):
        if self.resolve() == victim:
            raise OSError(13, "simulated permission denied")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", exploding_iterdir)
    names = [dst.name for _src, dst in _HOOK._plugin_mirrors(cache_sw, cache_sw / "plugins")]
    assert "shipwright-run" in names, "the readable plugin was starved by the broken one"
    assert "shipwright-compliance" not in names


def test_heal_plugins_continues_past_a_mirror_whose_copy_raises(tmp_path, monkeypatch):
    """Line-for-line the isolation guarantee the subprocess test proves end-to-end."""
    cache_sw, _mp = cache_and_marketplace(tmp_path)
    install(cache_sw, "shipwright-adopt", "0.2.1", OTHER_SRC)
    install(cache_sw, "shipwright-compliance", "0.2.2", OTHER_SRC)
    mirror(cache_sw, "shipwright-compliance", {"scripts/lib/keep.py": "KEEP = 1\n"})

    real_copytree = _HOOK.shutil.copytree
    calls = []

    def flaky_copytree(src, dst, *a, **k):
        calls.append(Path(dst).name)
        if Path(dst).name == "shipwright-adopt":
            raise OSError(13, "simulated unwritable mirror")
        return real_copytree(src, dst, *a, **k)

    monkeypatch.setattr(_HOOK.shutil, "copytree", flaky_copytree)

    assert _HOOK._heal_plugins(cache_sw, cache_sw / "plugins") is True
    assert "shipwright-adopt" in calls and "shipwright-compliance" in calls
    assert (cache_sw / "plugins" / "shipwright-compliance" / "scripts" / "lib"
            / "reaped.py").is_file(), "the failing mirror aborted the loop"


def test_main_continues_to_plugins_when_the_shared_copy_raises(tmp_path, monkeypatch, capsys):
    """The two trees repair independently — asserted at the guard, in-process."""
    import io
    cache_sw, mp_shared = cache_and_marketplace(tmp_path)
    make_shared(mp_shared)
    install_run(cache_sw)
    here = cache_sw / "shipwright-build" / "0.2.2" / "scripts" / "hooks" / "ensure_shared_cache.py"
    here.parent.mkdir(parents=True, exist_ok=True)
    here.touch()

    real_copytree = _HOOK.shutil.copytree

    def flaky_copytree(src, dst, *a, **k):
        if Path(dst).name == "shared":
            raise OSError(28, "simulated no space left")
        return real_copytree(src, dst, *a, **k)

    monkeypatch.setattr(_HOOK.shutil, "copytree", flaky_copytree)
    monkeypatch.setattr(_HOOK, "__file__", str(here))
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}"))

    assert _HOOK.main() == 0
    err = capsys.readouterr().err
    assert (cache_sw / "plugins").exists(), "a failed shared/ copy skipped the plugins repair"
    assert "shared" not in err.split("self-healed the plugin cache (")[-1].split(")")[0]
