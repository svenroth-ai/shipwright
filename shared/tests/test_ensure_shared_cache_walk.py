"""Unit-level semantics of the self-heal hook's completeness walk.

``test_ensure_shared_cache_integration`` proves the pieces COMPOSE by running
the real bootstrap as a subprocess. This module pins the walk's own contract,
where a subprocess test would only tell you "something went wrong":

- the walk must be **copytree-equivalent** — the same ``ignore`` callable,
  queried per directory, with ignored directories pruned BEFORE descent (a
  ``rglob()`` walks into ``.in_use`` first and only then discards it);
- it must be **tri-state** — an unreadable tree returns ``None``, never a short
  set, because an under-counted SOURCE manufactures a false "complete" verdict:
  precisely the bug this hook's fix is about, reintroduced via the error path;
- it must record **files only**, so a directory or broken symlink standing where
  a file belongs reads as missing rather than as present.

The values the hook is forced to duplicate (its ignore set, its version key) are
pinned in the sibling ``test_ensure_shared_cache_ssot_pins`` module.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling ensure_shared_cache_fixtures module

from ensure_shared_cache_fixtures import hook_module  # noqa: E402

#: One loader, shared with the fixtures module — two hand-rolled importlib
#: blocks for the same file is the divergence hazard this module exists to pin.
_HOOK = hook_module()


def _tree(root: Path, rels: list[str]) -> Path:
    for rel in rels:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x\n", encoding="utf-8")
    return root


# --------------------------------------------------------------------------
# the walk


def test_delivered_lists_plain_files_relative_and_posix(tmp_path: Path):
    _tree(tmp_path, ["a.py", "pkg/b.py", "pkg/deep/c.md"])
    assert _HOOK._delivered(tmp_path) == {"a.py", "pkg/b.py", "pkg/deep/c.md"}


def test_delivered_prunes_ignored_dirs_without_descending(tmp_path: Path):
    """``.in_use`` and ``__pycache__`` contribute nothing, however deep."""
    _tree(tmp_path, [
        "keep.py",
        ".in_use/8408",
        ".in_use/nested/deeper/still_ignored",
        "pkg/__pycache__/x.pyc",
        "pkg/__pycache__/sub/y.py",
        "pkg/real.py",
    ])
    assert _HOOK._delivered(tmp_path) == {"keep.py", "pkg/real.py"}


def test_delivered_never_enters_an_ignored_directory(tmp_path, monkeypatch):
    """Prune BEFORE descent — the property the explicit stack exists for.

    The set-equality test above is satisfied by a descend-then-filter walk too.
    This one fails it: a `rglob()` implementation walks INTO `.in_use` (and into
    a reaped `.venv` full of thousands of files) before discarding the results.
    """
    _tree(tmp_path, ["keep.py", ".in_use/8408", ".in_use/deep/deeper/x",
                     "pkg/__pycache__/a.pyc", "pkg/real.py"])
    visited = []
    real_iterdir = Path.iterdir

    def recording_iterdir(self):
        visited.append(self.name)
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", recording_iterdir)
    _HOOK._delivered(tmp_path)

    for forbidden in (".in_use", "__pycache__", "deep", "deeper"):
        assert forbidden not in visited, (
            f"the walk descended into {forbidden!r} before ignoring it — an ignored "
            "directory must be pruned, not filtered out afterwards"
        )
    assert "pkg" in visited, "sanity: the walk really did descend somewhere"


def test_delivered_drops_ignored_files_by_pattern(tmp_path: Path):
    _tree(tmp_path, ["m.py", "m.pyc", "m.pyo", ".orphaned_at", "sub/.orphaned_at"])
    assert _HOOK._delivered(tmp_path) == {"m.py"}


def test_delivered_is_none_for_a_tree_that_is_not_there(tmp_path: Path):
    """Tri-state: unknown must be distinguishable from empty."""
    assert _HOOK._delivered(tmp_path / "absent") is None
    (tmp_path / "afile").write_text("x", encoding="utf-8")
    assert _HOOK._delivered(tmp_path / "afile") is None


def test_delivered_returns_empty_set_for_an_empty_tree(tmp_path: Path):
    """...and empty must NOT be None, or a real empty dir reads as unknown."""
    (tmp_path / "empty").mkdir()
    assert _HOOK._delivered(tmp_path / "empty") == set()


def test_delivered_is_none_when_a_subdirectory_fails_mid_walk(tmp_path, monkeypatch):
    """An OSError DEEP in the walk must abandon the verdict, not shorten it.

    The root-level case is easy; this is the dangerous one. If the walk swallowed
    the error and returned the files it had gathered so far, a SOURCE tree would
    be under-counted and the destination would compare "complete" against a
    truncated expectation — the exact false-healthy verdict this whole change
    removes, re-entered through the error path.

    Also the general form of the symlink/junction-loop case: a loop terminates
    with an OSError (measured on Windows: FileNotFoundError at depth 18 once the
    path passes MAX_PATH; ELOOP/PATH_MAX on POSIX), so it lands here — unknown,
    no claim, no copy, exit 0. It is bounded, never a hang.
    """
    _tree(tmp_path, ["top.py", "deep/a.py", "deep/deeper/b.py"])
    victim = (tmp_path / "deep" / "deeper").resolve()
    real_iterdir = Path.iterdir

    def exploding_iterdir(self):
        if self.resolve() == victim:
            raise OSError(5, "simulated I/O error")
        return real_iterdir(self)

    monkeypatch.setattr(Path, "iterdir", exploding_iterdir)

    assert _HOOK._delivered(tmp_path) is None, (
        "a mid-walk failure produced a SHORT file set instead of 'unknown'"
    )
    assert _HOOK._incomplete(tmp_path, tmp_path) is None, "the verdict must stay unknown"


# --------------------------------------------------------------------------
# the verdict


def test_incomplete_true_when_a_delivered_file_is_missing(tmp_path: Path):
    src = _tree(tmp_path / "src", ["a.py", "b.py"])
    dst = _tree(tmp_path / "dst", ["a.py"])
    assert _HOOK._incomplete(src, dst) is True


def test_incomplete_false_when_every_delivered_file_is_present(tmp_path: Path):
    src = _tree(tmp_path / "src", ["a.py", "pkg/b.py"])
    dst = _tree(tmp_path / "dst", ["a.py", "pkg/b.py"])
    assert _HOOK._incomplete(src, dst) is False


def test_incomplete_ignores_extra_files_in_the_destination(tmp_path: Path):
    """The mirror legitimately carries cache-manager litter the source lacks."""
    src = _tree(tmp_path / "src", ["a.py"])
    dst = _tree(tmp_path / "dst", ["a.py", ".orphaned_at", "extra.py"])
    assert _HOOK._incomplete(src, dst) is False


def test_incomplete_true_when_the_destination_tree_is_absent(tmp_path: Path):
    src = _tree(tmp_path / "src", ["a.py"])
    assert _HOOK._incomplete(src, tmp_path / "nope") is True


def test_incomplete_is_none_when_the_source_cannot_be_read(tmp_path: Path):
    """Unknown ⇒ never claim health. An under-counted source is the old bug."""
    dst = _tree(tmp_path / "dst", ["a.py"])
    assert _HOOK._incomplete(tmp_path / "absent", dst) is None


def test_incomplete_true_when_a_directory_stands_where_a_file_belongs(tmp_path: Path):
    """``exists()`` is type-blind; a file-only walk is not (external review GPT-5)."""
    src = _tree(tmp_path / "src", ["a.py"])
    dst = tmp_path / "dst"
    (dst / "a.py").mkdir(parents=True)          # a DIRECTORY named a.py
    (dst / "a.py" / "inner").write_text("x", encoding="utf-8")
    assert _HOOK._incomplete(src, dst) is True


# --------------------------------------------------------------------------
# which installed version is the repair source


def test_version_key_orders_numerically_not_lexically():
    """``0.10.0`` is NEWER than ``0.2.0`` — lexically it sorts the other way.

    Latent while the loop skipped on ``dst.exists()`` (the pick was never read);
    load-bearing now that the picked version is the AUTHORITY on whether the
    mirror is complete. Picking an older version would compare the mirror
    against stale content and copy it over a perfectly good one.
    """
    assert _HOOK._version_key("0.10.0") > _HOOK._version_key("0.2.0")
    assert _HOOK._version_key("1.0.0") > _HOOK._version_key("0.29.1")
    assert _HOOK._version_key("0.2.1") > _HOOK._version_key("0.2.0")
    assert _HOOK._version_key("not-a-version") < _HOOK._version_key("0.0.1")


def test_plugin_mirrors_picks_the_numerically_newest_version(tmp_path: Path):
    cache = tmp_path / "cache" / "shipwright"
    for version in ("0.2.0", "0.10.0", "0.9.3"):
        (cache / "shipwright-x" / version / "scripts").mkdir(parents=True)
        (cache / "shipwright-x" / version / "scripts" / "m.py").write_text(
            f"V = '{version}'\n", encoding="utf-8")
    (cache / "not-a-plugin").mkdir(parents=True)

    pairs = list(_HOOK._plugin_mirrors(cache, cache / "plugins"))

    assert len(pairs) == 1, "only shipwright-* dirs are mirror sources"
    src, dst = pairs[0]
    assert src.name == "0.10.0", f"picked {src.name}, not the newest version"
    assert dst == cache / "plugins" / "shipwright-x"


def test_plugin_mirrors_yields_nothing_in_the_dev_repo_model(tmp_path: Path):
    """A repo root has no top-level ``shipwright-*`` dirs, so nothing is healed."""
    repo = tmp_path / "repo"
    (repo / "plugins" / "shipwright-build").mkdir(parents=True)
    (repo / "shared").mkdir()
    assert list(_HOOK._plugin_mirrors(repo, repo / "plugins")) == []
