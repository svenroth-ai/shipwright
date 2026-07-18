"""``load_shared_lib`` must win on sys.path PRECEDENCE, not just presence (ADR-045).

``lib`` is a regular package in every plugin (each ``scripts/lib`` has an ``__init__.py``),
so ``import lib.X`` binds to exactly the FIRST ``lib`` on ``sys.path``. The loader used to
insert ``shared/scripts`` only when absent, which silently does nothing once another
plugin's ``scripts`` dir already sits ahead of it — every shared-only module then raises
``ModuleNotFoundError: No module named 'lib.<name>'``.

That was latent for a long time because the existing call sites all load their shared
module early, while the ordering still happened to favour shared, and the result is
cached. It surfaced the moment a NEW shared module was loaded later in the same session
(the fold-map collector call). These cases pin the fix so it cannot regress.

@FR-01.10
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors import _lib_loader  # noqa: E402

_SHARED_SCRIPTS = _HERE.parents[2] / "shared" / "scripts"   # <repo>/shared/scripts


@pytest.fixture
def uncached(monkeypatch):
    """A loader with an empty module cache, so each case really performs the import."""
    monkeypatch.setattr(_lib_loader, "_CACHE", {})
    return _lib_loader


def _competing_lib(tmp_path: Path) -> str:
    """A decoy ``scripts`` dir holding a regular ``lib`` package with NO shared modules."""
    decoy = tmp_path / "plugin" / "scripts"
    (decoy / "lib").mkdir(parents=True)
    (decoy / "lib" / "__init__.py").write_text("", encoding="utf-8")
    (decoy / "lib" / "only_here.py").write_text("MARKER = 1\n", encoding="utf-8")
    return str(decoy)


def test_loads_shared_module_even_when_another_lib_precedes_on_syspath(uncached, tmp_path,
                                                                      monkeypatch):
    """The exact regression: a decoy ``lib`` ahead of shared/scripts must not win."""
    monkeypatch.setattr(sys, "path", [_competing_lib(tmp_path), *sys.path])
    monkeypatch.setitem(sys.modules, "lib", None)
    sys.modules.pop("lib", None)
    module = uncached.load_shared_lib("fr_fold_map")
    assert Path(module.__file__).parent == _SHARED_SCRIPTS / "lib"


@pytest.mark.parametrize("name", ["requirement_model", "fr_tag_grammar", "fr_fold_map"])
def test_every_shared_module_resolves_under_a_hostile_path(uncached, tmp_path,
                                                           monkeypatch, name):
    monkeypatch.setattr(sys, "path", [_competing_lib(tmp_path), *sys.path])
    assert Path(uncached.load_shared_lib(name).__file__).parent == _SHARED_SCRIPTS / "lib"


def test_shared_scripts_never_ends_up_shadowing_a_plugin_lib(uncached, tmp_path,
                                                             monkeypatch):
    """After the call, shared/scripts must not sit AHEAD of a plugin's own scripts dir.

    Front-precedence is scoped to the import itself; leaving it at the front would make a
    later bare ``from lib.X import …`` resolve to shared instead of the caller's own lib —
    trading one ADR-045 failure for its mirror image.
    """
    decoy = _competing_lib(tmp_path)
    monkeypatch.setattr(sys, "path", [decoy, *sys.path])
    uncached.load_shared_lib("fr_fold_map")
    shared = str(_SHARED_SCRIPTS)
    assert sys.path.index(decoy) < sys.path.index(shared)


def test_shared_scripts_stays_importable_after_the_call(uncached, tmp_path, monkeypatch):
    """The historical side effect is preserved — just at the END of the path."""
    monkeypatch.setattr(sys, "path", [_competing_lib(tmp_path)])
    uncached.load_shared_lib("fr_fold_map")
    assert str(_SHARED_SCRIPTS) in sys.path


def test_callers_prebound_lib_is_restored(uncached, tmp_path, monkeypatch):
    """The loader leaves no lasting ``sys.modules['lib']`` mutation."""
    sentinel = object()
    monkeypatch.setitem(sys.modules, "lib", sentinel)
    uncached.load_shared_lib("fr_fold_map")
    assert sys.modules["lib"] is sentinel
