"""Unit tests for the shared-module loader helper (trg-a67aa561).

Adopt scaffolders reuse ``shared/scripts/lib/`` helpers via a pollution-free
``spec_from_file_location`` loader. These tests pin the two sharp edges the
helper removes for every caller: a missing ``shared/`` tree must raise a legible
``ImportError`` (not a bare ``FileNotFoundError``), and a failing ``exec_module``
must not poison the ``sys.modules`` cache.
"""

import sys

import pytest

from lib import shared_loader
from lib.shared_loader import load_shared_module


def _write(base, rel, body):
    p = base.joinpath("shared", *rel.split("/"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def test_missing_shared_file_raises_importerror_not_filenotfound(tmp_path, monkeypatch):
    monkeypatch.setattr(shared_loader, "_REPO_ROOT", tmp_path)
    sentinel = "_test_shared_loader_missing"
    monkeypatch.delitem(sys.modules, sentinel, raising=False)
    with pytest.raises(ImportError) as ei:
        load_shared_module("scripts/lib/does_not_exist.py", sentinel)
    # Names the missing path + the shared dependency, not a bare OSError.
    assert "does_not_exist.py" in str(ei.value)
    assert not isinstance(ei.value, FileNotFoundError)
    # A failed lookup must not leave anything cached.
    assert sentinel not in sys.modules


def test_no_cache_poison_on_exec_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(shared_loader, "_REPO_ROOT", tmp_path)
    _write(tmp_path, "scripts/lib/boom.py", "raise RuntimeError('boom during exec')\n")
    sentinel = "_test_shared_loader_boom"
    monkeypatch.delitem(sys.modules, sentinel, raising=False)

    with pytest.raises(RuntimeError):
        load_shared_module("scripts/lib/boom.py", sentinel)
    # The half-initialised module must NOT be memoised under the sentinel...
    assert sentinel not in sys.modules
    # ...so a second call re-raises rather than returning a broken module.
    with pytest.raises(RuntimeError):
        load_shared_module("scripts/lib/boom.py", sentinel)


def test_successful_load_returns_module_and_caches(tmp_path, monkeypatch):
    monkeypatch.setattr(shared_loader, "_REPO_ROOT", tmp_path)
    _write(tmp_path, "scripts/lib/good.py", "VALUE = 42\n")
    sentinel = "_test_shared_loader_good"
    monkeypatch.delitem(sys.modules, sentinel, raising=False)
    try:
        mod1 = load_shared_module("scripts/lib/good.py", sentinel)
        assert mod1.VALUE == 42
        # Second call is a cache hit — same object, not a re-exec.
        mod2 = load_shared_module("scripts/lib/good.py", sentinel)
        assert mod1 is mod2
    finally:
        sys.modules.pop(sentinel, None)


def test_registers_before_exec_so_a_shared_module_resolves_its_own_name(tmp_path, monkeypatch):
    # Load-bearing: the helper registers the module in sys.modules BEFORE exec so
    # a shared module whose top-level code resolves its own sys.modules entry
    # (as gitattributes_union's @dataclass does for __module__) can load. A
    # register-AFTER-exec "simplification" would break this — pin it directly so
    # it is not only covered indirectly via the gitattributes import path.
    monkeypatch.setattr(shared_loader, "_REPO_ROOT", tmp_path)
    _write(
        tmp_path,
        "scripts/lib/needs_self.py",
        "import sys\n"
        "assert __name__ in sys.modules, 'module not registered before exec'\n"
        "OK = True\n",
    )
    sentinel = "_test_shared_loader_needs_self"
    monkeypatch.delitem(sys.modules, sentinel, raising=False)
    try:
        mod = load_shared_module("scripts/lib/needs_self.py", sentinel)
        assert mod.OK is True
    finally:
        sys.modules.pop(sentinel, None)


def test_every_rewired_scaffolder_still_resolves_its_shared_symbol():
    # The eight rewired scaffolders load their shared helper at import time.
    # Importing each must succeed on a normal install (shared/ present).
    from lib import (  # noqa: F401
        automerge_setup_scaffolder,
        baseline_generator,
        ci_workflow_scaffolder,
        claude_review_workflow_scaffolder,
        codeql_workflow_scaffolder,
        gitattributes_scaffolder,
        gitleaks_config_scaffolder,
        security_workflow_scaffolder,
    )

    # Each exposes the shared symbol it loaded — a spot-check that the rewire
    # kept the real load path working.
    assert automerge_setup_scaffolder.AUTOMERGE_SETUP_OUTPUT_PATH
