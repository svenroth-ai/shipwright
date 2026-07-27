"""Unit-level rules behind the repo-root pytest guard.

Sibling of `test_pytest_root_guard.py`, which drives whole pytest sessions
in child processes. This file pins the two pure functions those sessions
depend on -- `discover_test_roots` and `resolve_test_roots` -- including
against a synthetic repo tree, so the shapes that matter can be asserted
without depending on the real repo's current layout.

Split from the guard module at the 300-LOC guideline
(iterate-2026-07-27-pytest-root-composition).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_CONFTEST = REPO_ROOT / "conftest.py"


def _load_root_conftest():
    """Path-load the repo-root ``conftest.py`` under a sentinel name.

    Deliberately NOT a plain import: the subject of this module is
    ambiguity of top-level package names in this repo, so the test must not
    add to it. The sentinel is registered before ``exec_module`` because a
    module-level annotation would otherwise fail to resolve its own module.
    """
    spec = importlib.util.spec_from_file_location(
        "_sw_root_conftest_rules", ROOT_CONFTEST
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["_sw_root_conftest_rules"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def resolve():
    return _load_root_conftest().resolve_test_roots


# --------------------------------------------------------------------------- #
# Against the real repo
# --------------------------------------------------------------------------- #


def test_two_root_args_resolve_to_two_roots(resolve) -> None:
    assert len(resolve(["shared/tests", "integration-tests"], REPO_ROOT)) == 2


def test_parent_path_spanning_roots_is_refused(resolve) -> None:
    """`pytest .` from the repo root spans every root at once."""
    assert len(resolve(["."], REPO_ROOT)) > 1, (
        "An ancestor argument must expand to the roots it contains, else "
        "`pytest .` reproduces the original misleading failure."
    )


def test_node_id_selector_is_stripped(resolve) -> None:
    """Pin the `::` split with an argument where it CHANGES the outcome.

    A file node-id like `shared/tests/x.py::test_y` is a weak probe: even
    unsplit, `<repo>/shared/tests` is still one of its `.parents`, so the
    root is reached either way and the test would pass with the split
    deleted. A selector applied to the root directory itself is the
    discriminating case -- unsplit it matches no root at all.
    """
    roots = resolve(["integration-tests::test_y"], REPO_ROOT)
    assert len(roots) == 1, (
        f"The `::` selector must be split off before matching; got {sorted(roots)}"
    )


def test_file_node_id_reaches_its_root(resolve) -> None:
    roots = resolve(
        ["shared/tests/test_pytest_root_guard.py::test_x"], REPO_ROOT
    )
    assert len(roots) == 1


def test_node_id_selector_does_not_hide_a_second_root(resolve) -> None:
    roots = resolve(
        [
            "shared/tests/test_pytest_root_guard.py::test_x",
            "integration-tests/test_shared_contracts_consumers.py::test_y",
        ],
        REPO_ROOT,
    )
    assert len(roots) == 2


def test_unrelated_paths_are_ignored(resolve) -> None:
    assert resolve(["docs", "README.md"], REPO_ROOT) == set()


def test_same_root_twice_is_one_root(resolve) -> None:
    roots = resolve(["shared/tests/test_pytest_root_guard.py", "shared/tests"], REPO_ROOT)
    assert len(roots) == 1


def test_a_plugin_tests_dir_is_a_root(resolve) -> None:
    """Each plugin owns its own `scripts`/`lib`/`tools` namespace (ADR-044)."""
    roots = resolve(["plugins/shipwright-compliance/tests", "shared/tests"], REPO_ROOT)
    assert len(roots) == 2


def test_fixture_tests_dirs_are_not_roots(resolve) -> None:
    """Several roots ship fixture repos containing their own `tests/`.

    Counting a nested fixture directory as a root would make the guard
    refuse an ordinary single-root run -- its own worst failure mode, since
    it would then block the very commands CI relies on.
    """
    roots = resolve(["plugins/shipwright-compliance/tests"], REPO_ROOT)
    assert len(roots) == 1, f"nested fixture dirs leaked in: {sorted(roots)}"


def test_every_ci_root_survives_alone(resolve) -> None:
    for root in (
        "integration-tests",
        "shared/tests",
        "shared/scripts/tests",
        "shared/scripts/tools/tests",
    ):
        assert len(resolve([root], REPO_ROOT)) == 1, f"{root} would be refused alone"


def test_discovered_roots_cover_the_ci_matrix() -> None:
    """Registry drift guard: every root CI invokes must be discovered.

    `ci.yml` loops over shared/tests, shared/scripts/tests and
    shared/scripts/tools/tests, then runs integration-tests separately. A
    root CI runs but the guard does not know about would silently permit
    the broken combination.
    """
    discovered = _load_root_conftest().discover_test_roots(REPO_ROOT)
    relative = {p.relative_to(REPO_ROOT).as_posix() for p in discovered}
    for expected in (
        "integration-tests",
        "shared/tests",
        "shared/scripts/tests",
        "shared/scripts/tools/tests",
    ):
        assert expected in relative, f"{expected} missing from {sorted(relative)}"


# --------------------------------------------------------------------------- #
# Against a synthetic tree -- shapes the real repo may not currently have
# --------------------------------------------------------------------------- #


@pytest.fixture
def fake_repo(tmp_path: Path) -> Path:
    """A miniature repo carrying every shape discovery must judge."""
    for rel in (
        "integration-tests",
        "shared/tests",
        "shared/scripts/tests",
        "plugins/demo/tests",
        # Third-party tests inside a plugin virtualenv: NOT a repo root.
        "plugins/demo/.venv/Lib/site-packages/somepkg/tests",
        "plugins/demo/node_modules/dep/tests",
        # A fixture repo nested inside a real root: NOT a separate root.
        "plugins/demo/tests/fixtures/mini_repo/tests",
        "shared/tests/fixtures/app/tests",
        # Not a test root at all.
        "docs",
    ):
        (tmp_path / rel).mkdir(parents=True)
    return tmp_path


def test_skip_dirs_keep_vendored_tests_out_of_discovery(fake_repo: Path) -> None:
    """A `tests/` dir inside `.venv` / `node_modules` is someone else's.

    Counting one would refuse an ordinary single-root session -- the
    guard's worst possible failure, since it would block CI itself.
    """
    discovered = _load_root_conftest().discover_test_roots(fake_repo)
    relative = {p.relative_to(fake_repo).as_posix() for p in discovered}
    assert relative == {
        "integration-tests",
        "shared/tests",
        "shared/scripts/tests",
        "plugins/demo/tests",
    }, sorted(relative)


def test_discovery_does_not_descend_into_skipped_dirs(fake_repo: Path) -> None:
    """Pruning, not post-filtering: startup must not walk a virtualenv."""
    conftest = _load_root_conftest()
    sentinel = fake_repo / "plugins" / "demo" / ".venv" / "SENTINEL"
    (sentinel / "tests").mkdir(parents=True)
    discovered = conftest.discover_test_roots(fake_repo)
    assert not any(".venv" in p.parts for p in discovered), sorted(discovered)


def test_relative_args_resolve_against_the_invocation_dir(fake_repo: Path) -> None:
    conftest = _load_root_conftest()
    roots = conftest.resolve_test_roots(["tests"], fake_repo, fake_repo / "shared")
    assert {p.relative_to(fake_repo).as_posix() for p in roots} == {"shared/tests"}


def test_dot_arg_inside_a_root_reaches_only_that_root(fake_repo: Path) -> None:
    """`cd shared/tests && pytest .` is a SINGLE-root session.

    Resolving `.` against the repo root instead would make it an ancestor
    of every root and refuse a perfectly ordinary run.
    """
    conftest = _load_root_conftest()
    roots = conftest.resolve_test_roots(["."], fake_repo, fake_repo / "shared" / "tests")
    assert {p.relative_to(fake_repo).as_posix() for p in roots} == {"shared/tests"}


def test_relative_args_from_a_subdir_can_still_span_roots(fake_repo: Path) -> None:
    conftest = _load_root_conftest()
    roots = conftest.resolve_test_roots(
        ["tests", "../integration-tests"], fake_repo, fake_repo / "shared"
    )
    assert len(roots) == 2, sorted(roots)


# --------------------------------------------------------------------------- #
# The collected-items backstop
# --------------------------------------------------------------------------- #


def test_roots_containing_maps_collected_files_to_their_roots(fake_repo: Path) -> None:
    """`roots_containing` takes resolved paths -- no argument parsing.

    This is what the collection backstop uses, so that targets pytest
    derives itself (`testpaths`, `--pyargs`, a `-k` selection) are judged
    by where their files actually live.
    """
    conftest = _load_root_conftest()
    roots = conftest.roots_containing(
        [
            fake_repo / "shared" / "tests" / "test_a.py",
            fake_repo / "integration-tests" / "test_b.py",
        ],
        fake_repo,
    )
    assert {p.relative_to(fake_repo).as_posix() for p in roots} == {
        "shared/tests",
        "integration-tests",
    }


def test_roots_containing_ignores_files_outside_any_root(fake_repo: Path) -> None:
    conftest = _load_root_conftest()
    roots = conftest.roots_containing([fake_repo / "docs" / "note.md"], fake_repo)
    assert roots == set()


def test_roots_containing_treats_one_root_as_one(fake_repo: Path) -> None:
    conftest = _load_root_conftest()
    roots = conftest.roots_containing(
        [
            fake_repo / "shared" / "tests" / "test_a.py",
            fake_repo / "shared" / "tests" / "sub" / "test_b.py",
        ],
        fake_repo,
    )
    assert len(roots) == 1
