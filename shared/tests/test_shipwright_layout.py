"""The new-then-old lookup behind ``shipwright_paths.path()`` (campaign root-files-into-config, R1c-1).

Every row of the state table in ``shared/scripts/lib/shipwright_layout.py`` with real files in a temp
project, the shared pointer fixture set (BRIEF 14.1), the error contract, and the one-layout-module-per-
tree rule. BRIEF: ``.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "shared" / "scripts" / "lib"
for _p in (REPO / "shared" / "scripts", REPO / "shared" / "testkit"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib import shipwright_paths as sp  # noqa: E402
from pointer_stub_cases import cases  # noqa: E402

CFG = b'{"status": "complete"}\n'
OTHER = b'{"status": "in_progress"}\n'
STUB = next(c.data for c in cases() if c.id == "lf_canonical")
MOVING = sp.keys_of(moves=True)


def _put(root: Path, rel: str, data: bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _layout(root: Path, key: str, *, new: bytes | None, old: bytes | None) -> tuple[Path, Path]:
    n, o = root / sp.new_rel(key), root / sp.legacy_rel(key)
    if new is not None:
        _put(root, sp.new_rel(key), new)
    if old is not None:
        _put(root, sp.legacy_rel(key), old)
    return n, o


def _code(fn):
    with pytest.raises(sp.LayoutError) as exc:
        fn()
    return exc.value


# ---- the state table, every moving key ------------------------------------------------------------
@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("key", MOVING)
@pytest.mark.parametrize("new, old, want", [
    (None, None, "old"),      # fresh repo: writers keep creating the legacy file until R3
    (None, CFG, "old"),
    (CFG, None, "new"),
], ids=["neither", "root_only", "new_only"])
def test_path_follows_the_file(tmp_path, key, new, old, want):
    n, o = _layout(tmp_path, key, new=new, old=old)
    assert sp.path(key, tmp_path) == (n if want == "new" else o)
    assert sp.path(key, str(tmp_path)) == sp.path(key, tmp_path)


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("key", MOVING)
@pytest.mark.parametrize("new, old", [(CFG, OTHER), (CFG, CFG)], ids=["different", "identical"])
def test_two_copies_are_a_loud_error_even_when_identical(tmp_path, key, new, old):
    """Identical too: a writer would update only the new copy and the next read would fail anyway."""
    n, o = _layout(tmp_path, key, new=new, old=old)
    err = _code(lambda: sp.path(key, tmp_path))
    assert (err.code, err.key, err.paths) == ("both_copies", key, (str(n), str(o)))
    assert str(n) in str(err) and str(o) in str(err) and "delete" in str(err)


@pytest.mark.covers("FR-01.11")
def test_files_that_do_not_move_ignore_a_new_place_copy(tmp_path):
    for key in sp.keys_of(moves=False, include_retired=True):
        _put(tmp_path, f".shipwright/config/{sp.name(key)}", CFG)
        assert sp.path(key, tmp_path) == tmp_path / sp.legacy_rel(key)


# ---- the pointer stub (only the root run_config can be one, BRIEF 14.1) ---------------------------
_ROOT_STUB_ROWS = [c for c in cases() if c.location == "root"]


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("case", _ROOT_STUB_ROWS, ids=[c.id for c in _ROOT_STUB_ROWS])
@pytest.mark.parametrize("migrated", [True, False], ids=["new_present", "new_absent"])
def test_root_run_config_per_shared_fixture_row(tmp_path, case, migrated):
    n, o = _layout(tmp_path, "run_config", new=CFG if migrated else None, old=case.data)
    want = {("stub", True): n, ("stub", False): "incomplete_migration", ("too_new", True): "pointer_too_new",
            ("too_new", False): "pointer_too_new", ("edited", True): "pointer_edited",
            ("edited", False): "pointer_edited", ("not_stub", True): "both_copies", ("not_stub", False): o}
    expected = want[(case.expect, migrated)]
    if isinstance(expected, Path):
        assert sp.path("run_config", tmp_path) == expected, case.why
    else:
        assert _code(lambda: sp.path("run_config", tmp_path)).code == expected, case.why


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("key", MOVING)
@pytest.mark.parametrize("old", [None, CFG], ids=["root_absent", "root_present"])
def test_a_stub_at_the_new_path_is_never_config(tmp_path, key, old):
    row = next(c for c in cases() if c.location == "new")
    _layout(tmp_path, key, new=row.data, old=old)
    assert _code(lambda: sp.path(key, tmp_path)).code == "stub_at_new_path"


@pytest.mark.covers("FR-01.11")
def test_incomplete_migration_names_the_missing_copy_and_the_recovery(tmp_path):
    n, _ = _layout(tmp_path, "run_config", new=None, old=STUB)
    err = _code(lambda: sp.path("run_config", tmp_path))
    assert str(n) in str(err) and "Restore" in str(err) and "writes are refused" in str(err)


@pytest.mark.covers("FR-01.11")
def test_a_stub_on_another_key_is_ordinary_content(tmp_path):
    """Only the root run_config can be a stub; elsewhere the bytes are the caller's to parse."""
    _, o = _layout(tmp_path, "build_config", new=None, old=STUB)
    assert sp.path("build_config", tmp_path) == o


@pytest.mark.covers("FR-01.11")
def test_the_stub_text_is_never_followed(tmp_path):
    """BRIEF 14.2: ``moved_to:`` is for humans; the new place is fixed by the registry."""
    evil = STUB.replace(b"moved_to: .shipwright/config/", b"moved_to: ../../elsewhere/")
    n, _ = _layout(tmp_path, "run_config", new=CFG, old=evil)
    assert sp.path("run_config", tmp_path) == n == tmp_path / ".shipwright" / "config" / sp.name("run_config")


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("big", [b'{"pad": "' + b"x" * 100_000 + b'"}\n',            # indented-style
                                 b'{"pad": "' + b"x" * 100_000 + b'"}',              # minified, one line
                                 b'\xef\xbb\xbf  {"pad": "' + b"x" * 100_000 + b'"}'],  # BOM + spaces
                         ids=["newline_at_end", "single_line", "bom_and_space"])
def test_a_large_root_config_is_judged_on_one_short_read(tmp_path, monkeypatch, big):
    _, o = _layout(tmp_path, "run_config", new=None, old=big)
    sizes: list[int] = []
    real = open

    class _Counting:
        def __init__(self, fh):
            self._fh = fh

        def read(self, n=-1):
            data = self._fh.read(n)
            sizes.append(len(data))
            return data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self._fh.close()

    monkeypatch.setattr(sp._LAYOUT, "open", lambda p, mode="r", *a, **k: _Counting(real(p, mode, *a, **k)),
                        raising=False)
    assert sp.path("run_config", tmp_path) == o
    assert sum(sizes) <= 2048, sizes


@pytest.mark.covers("FR-01.11")
def test_a_directory_or_other_non_file_is_no_copy(tmp_path):
    """Only regular files count: a directory of that name is neither present nor read (never blocks)."""
    (tmp_path / sp.new_rel("run_config")).mkdir(parents=True)
    _, o = _layout(tmp_path, "run_config", new=None, old=CFG)
    assert sp.path("run_config", tmp_path) == o


# ---- the other entry points use the same lookup ---------------------------------------------------
@pytest.mark.covers("FR-01.11")
def test_main_path_and_json_path_or_none_use_the_lookup(tmp_path):
    main = tmp_path / "main"
    n, _ = _layout(main, "model_config", new=CFG, old=None)
    assert sp.main_path("model_config", tmp_path / "wt", main) == n
    assert sp.main_path("model_config", main, None) == n
    nb, _ = _layout(tmp_path, "build_config", new=CFG, old=None)
    assert sp.json_path_or_none("build_config", tmp_path) == nb
    assert sp.json_path_or_none("audit_config", tmp_path) is None
    assert sp.json_path_or_none("no_such_name", tmp_path) == tmp_path / "shipwright_no_such_name.json"
    _layout(tmp_path, "plan_config", new=CFG, old=OTHER)
    assert _code(lambda: sp.json_path_or_none("plan_config", tmp_path)).code == "both_copies"


@pytest.mark.covers("FR-01.11")
def test_a_writer_and_a_reader_meet_in_both_layouts(tmp_path):
    """Round trip through path(): what a writer writes, a reader reads, before and after a move."""
    for migrated in (False, True):
        root = tmp_path / str(migrated)
        root.mkdir()
        if migrated:
            _put(root, sp.new_rel("test_config"), b"{}")
        written = sp.path("test_config", root)
        written.write_text(json.dumps({"v": migrated}), encoding="utf-8")
        assert json.loads(sp.path("test_config", root).read_text(encoding="utf-8")) == {"v": migrated}
        new, old = root / sp.new_rel("test_config"), root / sp.legacy_rel("test_config")
        if migrated:
            assert written == new and not old.exists()
        else:
            assert written == old and not new.exists()


# ---- the error type -------------------------------------------------------------------------------
@pytest.mark.covers("FR-01.11")
def test_layout_error_is_not_caught_as_missing_file_bad_json_or_lock_timeout():
    assert issubclass(sp.LayoutError, Exception)
    for common in (OSError, ValueError, RuntimeError):
        assert not issubclass(sp.LayoutError, common), common


@pytest.mark.covers("FR-01.11")
def test_no_production_code_writes_the_new_place_before_r3():
    """R1c-1 alone is safe only because nothing creates ``.shipwright/config/`` yet (frozen root constants
    and the locked writers still name the root until R1c-2/R3): no production file of ANY type (code, prompts,
    templates, hooks.json, workflows) names the folder, and nothing outside the resolver asks for the new paths."""
    allowed = {"shared/scripts/lib/shipwright_paths.py", "shared/scripts/lib/shipwright_layout.py",
               "shared/scripts/lib/shipwright_pointer.py"}  # the resolver, its lookup, the stub renderer
    scope = ["--", "plugins", "shared", "scripts", ".github", ":!*/tests/*", ":!shared/testkit/*"]
    # R1c-2 (D1): the dev-server state's new place is a FILE in the already-used runtime folder, so name it
    named = subprocess.run(["git", "grep", "-l", "--untracked", "-E",
                            r"shipwright[/\\]+config|runtime[/\\]+shipwright_dev_server", *scope],
                           capture_output=True, text=True, cwd=str(REPO)).stdout.split()
    assert [h for h in named if h not in allowed] == []
    asked = subprocess.run(["git", "grep", "-l", "--untracked", "-E", r"\b(new_rel|known_rels|all_known_rels)\(", *scope],
                           capture_output=True, text=True, cwd=str(REPO)).stdout.split()
    assert [h for h in asked if h not in allowed] == []


# ---- one layout module per tree --------------------------------------------------------------------
def _run(body: str) -> dict:
    code = "import json, sys, importlib, importlib.util\n" + textwrap.dedent(body)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, timeout=60, cwd=str(REPO))
    assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
    return json.loads(out.stdout.decode("utf-8", "replace").strip().splitlines()[-1])


@pytest.mark.covers("FR-01.11")
def test_every_alias_shares_one_layout_module_and_another_tree_has_its_own(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    for n in ("shipwright_paths.py", "shipwright_layout.py", "shipwright_pointer.py"):
        (other / n).write_text((LIB / n).read_text(encoding="utf-8"), encoding="utf-8")
    res = _run(f"""
        sys.path.insert(0, {str(REPO / "shared" / "scripts")!r})
        from lib import shipwright_paths as a
        sys.path.insert(0, {str(LIB)!r}); import shipwright_paths as b
        spec = importlib.util.spec_from_file_location("_x_hand", {str(LIB / "shipwright_paths.py")!r})
        c = importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
        spec = importlib.util.spec_from_file_location("_y_other", {str(other / "shipwright_paths.py")!r})
        d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
        print(json.dumps({{"ab": a.LayoutError is b.LayoutError, "ac": a.LayoutError is c.LayoutError,
                           "ad": a.LayoutError is d.LayoutError, "d_name": d.LayoutError.__name__}}))
    """)
    assert res == {"ab": True, "ac": True, "ad": False, "d_name": "LayoutError"}


@pytest.mark.covers("FR-01.11")
def test_a_missing_sibling_is_an_import_error_the_guarded_hooks_catch(tmp_path):
    """A half-copied plugin cache: the resolver import fails as ImportError, not FileNotFoundError."""
    (tmp_path / "shipwright_paths.py").write_text((LIB / "shipwright_paths.py").read_text(encoding="utf-8"),
                                                  encoding="utf-8")
    res = _run(f"""
        sys.path.insert(0, {str(tmp_path)!r})
        try:
            import shipwright_paths
            print(json.dumps({{"raised": None}}))
        except ImportError as exc:
            print(json.dumps({{"raised": type(exc).__name__, "left": "shipwright_paths" in sys.modules}}))
    """)
    assert res == {"raised": "ImportError", "left": False}
