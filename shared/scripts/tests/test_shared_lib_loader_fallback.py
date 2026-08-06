"""``shared_lib_loader``'s fallback must survive a shadowed ``lib`` — including
for lib modules that import a sibling.

The regression these pin (trg-dc013d82): ``file_lock`` and ``atomic_write`` each
grew an intra-package import, and the fallback — which used to load each module
as a lone top-level sentinel — then died with ``ModuleNotFoundError: No module
named 'file_lock_registry'`` / ``'durable_publish'``. It was invisible to every
pytest root that change ran, because the fallback only fires once some OTHER
``lib`` package has claimed ``sys.modules['lib']`` — which is what a plugin test
session does. Worse, the in-process triage producers that reach the store this
way wrap the append in ``except Exception``, so the failure would have surfaced
as silently missing findings rather than as a crash.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from shared_lib_loader import load_shared_lib  # noqa: E402

#: Every shared lib module that triage's write path reaches through the loader.
#: `file_lock` and `atomic_write` are the two that carry sibling imports.
_LOADED_VIA_FALLBACK = ("file_lock", "atomic_write", "triage_header", "jsonl_records")


@pytest.fixture
def shadowed_lib(monkeypatch, tmp_path):
    """Bind ``sys.modules['lib']`` to a decoy that has none of these modules.

    This is the real precondition, not a contrivance: any plugin test session
    that imported its own ``scripts/lib`` first leaves exactly this state, and it
    is what forces ``load_shared_lib`` off its happy path onto the fallback.
    """
    decoy = types.ModuleType("lib")
    decoy.__path__ = [str(tmp_path)]
    monkeypatch.setitem(sys.modules, "lib", decoy)
    # Drop anything the happy path may have cached, so the fallback really runs.
    for name in list(sys.modules):
        if name.startswith("lib.") or name.startswith("_shipwright_shared_lib"):
            monkeypatch.delitem(sys.modules, name, raising=False)
    # `shared/scripts/lib` must NOT be importable as a flat path either — the
    # loader deliberately never puts it there (it holds `config.py`/`state.py`,
    # so doing so would just relocate the shadowing).
    lib_dir = str(_SCRIPTS / "lib").replace("\\", "/")
    monkeypatch.setattr(
        sys, "path",
        [p for p in sys.path if p.replace("\\", "/").rstrip("/") != lib_dir])
    return decoy


@pytest.mark.parametrize("module_name", _LOADED_VIA_FALLBACK)
def test_fallback_loads_a_lib_module_past_a_shadowing_lib(shadowed_lib, module_name):
    """Each module triage reaches through the loader still loads when `lib` is taken."""
    module = load_shared_lib(module_name)
    assert module is not None
    # Loaded into the private package, never into the shadowed `lib` namespace.
    assert module.__name__.startswith("_shipwright_shared_lib")
    assert sys.modules["lib"] is shadowed_lib, "the decoy must be left untouched"


def test_a_sibling_import_resolves_inside_the_private_package(shadowed_lib):
    """The specific breakage: a lib module that imports a sibling.

    ``file_lock`` needs ``file_lock_registry``; ``atomic_write`` needs
    ``durable_publish``. Both must come out of the private package, so the
    fallback is no longer restricted to stdlib-only leaves.
    """
    file_lock = load_shared_lib("file_lock")
    atomic_write = load_shared_lib("atomic_write")

    assert file_lock.FileLock is not None
    assert atomic_write.durable_atomic_write is not None
    assert sys.modules["_shipwright_shared_lib.file_lock_registry"]
    assert sys.modules["_shipwright_shared_lib.durable_publish"]


def test_the_loader_never_puts_lib_on_sys_path(shadowed_lib):
    """`shared/scripts/lib` holds `config.py` and `state.py`.

    Putting that directory on the global path would relocate the very collision
    this loader exists to survive, so the fix for the sibling-import breakage
    must not have taken that shortcut.
    """
    load_shared_lib("file_lock")
    lib_dir = str(_SCRIPTS / "lib").replace("\\", "/").rstrip("/")
    assert not any(p.replace("\\", "/").rstrip("/") == lib_dir for p in sys.path)


def test_an_unknown_module_still_raises_importerror(shadowed_lib):
    """A typo must fail loudly rather than resolve to something surprising."""
    with pytest.raises(ImportError):
        load_shared_lib("definitely_not_a_shared_lib_module")
