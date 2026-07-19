"""Direct unit tests for ``shared/scripts/lib/planning_discovery.py``.

The golden corpus proves the 15 CALL SITES did not change behaviour. It does not
exercise the helper's parameter matrix directly: a flag combination no current
caller uses is untested there by construction, and both ``ValueError`` guards are
unreachable through the call sites at all. This module covers the surface itself.

Added in code review of campaign S2 (finding 4).
"""

from __future__ import annotations

import pytest

from lib.planning_discovery import (
    ITERATE_DIRNAME,
    SPEC_FILENAME,
    iter_spec_files,
    iter_split_dirs,
)


def _planning(root):
    """The canonical planning dir, ``<root>/.shipwright/planning`` — not created.

    Built as the real on-disk shape rather than a bare top-level directory that
    never exists in practice, so these fixtures mirror the S1 corpus layout and
    the directory these functions are actually handed at every call site.
    """
    return root / ".shipwright" / "planning"


def _planning_as_file(root):
    """Put a regular FILE where the planning DIR belongs, and return it."""
    planning = _planning(root)
    planning.parent.mkdir(parents=True, exist_ok=True)
    planning.write_text("not a dir", encoding="utf-8")
    return planning


def _tree(root, *splits, nested=False, loose=False):
    """Build the planning dir with the given split names, each with a spec.md."""
    planning = _planning(root)
    planning.mkdir(parents=True)
    for name in splits:
        d = planning / name
        d.mkdir()
        (d / SPEC_FILENAME).write_text("# spec\n", encoding="utf-8")
    if nested:
        deep = planning / "nest" / "deeper"
        deep.mkdir(parents=True)
        (deep / SPEC_FILENAME).write_text("# deep\n", encoding="utf-8")
    if loose:
        (planning / SPEC_FILENAME).write_text("# loose\n", encoding="utf-8")
    return planning


def _names(paths):
    return [p.parent.name for p in paths]


# --------------------------------------------------------------------------
# guard: the axis that decides degrade-vs-raise
# --------------------------------------------------------------------------

def test_guard_is_dir_degrades_on_absent_and_on_a_planning_file(tmp_path):
    assert list(iter_split_dirs(_planning(tmp_path))) == []
    assert list(iter_split_dirs(_planning_as_file(tmp_path))) == []


def test_guard_exists_degrades_on_absent_but_raises_on_a_planning_file(tmp_path):
    """The frozen latent bug: 4 call sites reach iterdir() on a regular file."""
    assert list(iter_split_dirs(_planning(tmp_path), guard="exists")) == []

    with pytest.raises(NotADirectoryError):
        list(iter_split_dirs(_planning_as_file(tmp_path), guard="exists"))


def test_guard_none_raises_on_absent_and_on_a_planning_file(tmp_path):
    """Only state.detect_state uses this; nothing else exercises it."""
    with pytest.raises(FileNotFoundError):
        list(iter_split_dirs(_planning(tmp_path), guard="none"))

    with pytest.raises(NotADirectoryError):
        list(iter_split_dirs(_planning_as_file(tmp_path), guard="none"))


def test_guard_exceptions_surface_on_first_iteration_not_at_call_time(tmp_path):
    """Lazy by design. Every caller iterates immediately, so the exception still
    escapes the same public function with the same type -- but the generator is
    constructed without touching the filesystem."""
    gen = iter_split_dirs(_planning(tmp_path), guard="none")
    with pytest.raises(FileNotFoundError):
        next(gen)


# --------------------------------------------------------------------------
# ValueError guards -- unreachable through any call site
# --------------------------------------------------------------------------

def test_invalid_guard_rejected(tmp_path):
    with pytest.raises(ValueError, match="guard must be one of"):
        list(iter_split_dirs(_tree(tmp_path, "01-a"), guard="is_file"))


def test_invalid_require_rejected(tmp_path):
    with pytest.raises(ValueError, match="require must be one of"):
        list(iter_spec_files(_tree(tmp_path, "01-a"), require="exists_ok"))


# --------------------------------------------------------------------------
# sort / include_iterate / require / recursive
# --------------------------------------------------------------------------

def test_sort_true_orders_and_sort_false_preserves_iterdir_order(tmp_path):
    planning = _tree(tmp_path, "03-c", "01-a", "02-b")
    assert _names(iter_spec_files(planning)) == ["01-a", "02-b", "03-c"]
    unsorted = _names(iter_spec_files(planning, sort=False))
    assert sorted(unsorted) == ["01-a", "02-b", "03-c"]


def test_include_iterate_toggles_the_iterate_dir(tmp_path):
    planning = _tree(tmp_path, "01-a", ITERATE_DIRNAME)
    assert ITERATE_DIRNAME in _names(iter_spec_files(planning))
    assert ITERATE_DIRNAME not in _names(iter_spec_files(planning, include_iterate=False))


def test_non_directory_entries_are_always_skipped(tmp_path):
    planning = _tree(tmp_path, "01-a")
    (planning / "stray.md").write_text("x", encoding="utf-8")
    assert [d.name for d in iter_split_dirs(planning)] == ["01-a"]


def test_require_is_file_rejects_a_directory_named_spec_md(tmp_path):
    """The spec-dir divergence: exists() accepts a DIRECTORY named spec.md,
    which then explodes at read_text. Two call sites guard; thirteen do not."""
    planning = _planning(tmp_path)
    (planning / "01-a" / SPEC_FILENAME).mkdir(parents=True)
    assert _names(iter_spec_files(planning, require="exists")) == ["01-a"]
    assert list(iter_spec_files(planning, require="is_file")) == []


def test_recursive_descends_and_matches_a_loose_planning_spec(tmp_path):
    planning = _tree(tmp_path, "01-a", nested=True, loose=True)
    flat = list(iter_spec_files(planning))
    deep = list(iter_spec_files(planning, recursive=True))
    assert _names(flat) == ["01-a"]
    rel = sorted(p.relative_to(planning).as_posix() for p in deep)
    assert rel == ["01-a/spec.md", "nest/deeper/spec.md", "spec.md"]


def test_recursive_still_honours_include_iterate_at_any_depth(tmp_path):
    planning = _tree(tmp_path, "01-a", ITERATE_DIRNAME)
    out = iter_spec_files(planning, recursive=True, include_iterate=False)
    assert ITERATE_DIRNAME not in _names(out)


def test_hidden_splits_are_included_by_both_modes(tmp_path):
    """pathlib's glob/rglob DO match a leading dot, so there is no hidden-dir
    axis. Comments in the tree once claimed the opposite."""
    planning = _tree(tmp_path, "01-a", ".hidden-split")
    assert ".hidden-split" in _names(iter_spec_files(planning))
    assert ".hidden-split" in _names(iter_spec_files(planning, recursive=True))


def test_laziness_short_circuits_without_walking_every_split(tmp_path):
    """fr_gates relies on this: any()/next() must stop at the first hit."""
    planning = _tree(tmp_path, "01-a", "02-b", "03-c")
    gen = iter_spec_files(planning, sort=False)
    assert next(gen, None) is not None
    gen.close()


# --------------------------------------------------------------------------
# Ordering equivalence -- the axis the corpus is structurally blind to
# --------------------------------------------------------------------------

#: Split-name pairs where one name is a proper prefix of the other. Raw STRING
#: comparison of the joined paths inverts these (``-`` 0x2D sorts below both
#: ``/`` 0x2F and ``\`` 0x5C), so they are the only shapes that could expose a
#: difference between sorting split DIRS and sorting full spec.md PATHS.
_PREFIX_PAIRS = [
    ("core", "core-api"),
    ("01-live", "01-live-v2"),
    ("api", "api2"),
    ("a", "a-b"),
]


@pytest.mark.parametrize("first,second", _PREFIX_PAIRS)
def test_sorting_split_dirs_equals_sorting_full_spec_paths(tmp_path, first, second):
    """``read_top_level_spec`` used to sort full ``*/spec.md`` paths; it now sorts
    split dirs and appends the filename. Those are equivalent because
    ``PurePath.__lt__`` compares a PARTS LIST, not the joined string: with a
    constant trailing component, ``[planning, X, spec.md]`` vs
    ``[planning, Y, spec.md]`` reduces to ``X`` vs ``Y``.

    Reviewed as a suspected silent behaviour change and falsified. No fixture in
    the golden corpus contains a proper-prefix split pair, so the corpus cannot
    see this axis -- which is exactly why it is pinned here instead. Do NOT
    "fix" it by adding a redundant sort: that would imply a bug that does not
    exist, and S2b leans on this equivalence when it converges the walks.
    """
    planning = _tree(tmp_path, first, second)

    by_dirs = list(iter_spec_files(planning))
    by_full_paths = sorted(planning.glob(f"*/{SPEC_FILENAME}"))

    assert by_dirs == by_full_paths
    assert _names(by_dirs) == sorted([first, second])


def test_prefix_pairs_are_a_real_trap_for_string_sorting(tmp_path):
    """Guards the guard: if raw-string ordering ever stopped diverging, the test
    above would silently stop testing anything. At least one pair must invert
    under naive string comparison."""
    planning = _tree(tmp_path, "core", "core-api")
    paths = sorted(planning.glob(f"*/{SPEC_FILENAME}"))
    by_str = sorted(paths, key=str)
    assert paths != by_str, "string vs parts ordering no longer diverges"
