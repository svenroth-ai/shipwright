"""The repo-root pytest guard refuses a session that spans two test roots.

Background (iterate-2026-07-27-pytest-root-composition): running

    uv run pytest shared/tests integration-tests -m "not slow and not cross_plugin"

as ONE invocation fails 21 tests that the change under test never touched.
The cause is structural, not incidental: `shared/tests/__init__.py` makes
pytest prepend ``<repo>/shared`` to ``sys.path``, which exposes
``shared/scripts`` as the top-level namespace package ``scripts``. Because
``shared/scripts/lib/__init__.py`` exists, ``scripts.lib`` is a REGULAR
package pinned to that one directory and cached in ``sys.modules`` on first
touch -- so ``shared/contracts/compliance.py`` can never reach the
compliance plugin's ``scripts.lib.data_collector``, no matter what it
prepends to ``sys.path``.

`.github/workflows/ci.yml` already runs one test root per pytest process
and documents why. These tests pin the refusal so the violation reports
itself instead of surfacing as 21 misleading assertion errors.

**On the `slow` marker.** These tests spawn pytest child processes, which
`pyproject.toml` defines as the `slow` case. They are deliberately left
unmarked: CI runs `-m "not slow and not cross_plugin"`, so marking them
would remove the guard's only coverage from the very pipeline the guard
protects. They are kept cheap instead -- every child process runs
`--collect-only` except the one execution check -- and the whole module
finishes in a few seconds.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _run_pytest(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Collect-only pytest in a child process.

    ``--collect-only`` still fires ``pytest_sessionstart``, so the guard is
    exercised at full fidelity while costing no test execution.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *args],
        cwd=str(cwd or REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


# --------------------------------------------------------------------------- #
# Behaviour: a real two-root session is refused (AC1)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def two_root_run() -> subprocess.CompletedProcess:
    return _run_pytest("shared/tests", "integration-tests")


def test_multi_root_session_is_refused(two_root_run) -> None:
    assert two_root_run.returncode != 0, (
        "A session spanning shared/tests AND integration-tests must be "
        f"refused, got exit 0.\nstdout:\n{two_root_run.stdout}"
    )


def test_refusal_is_not_a_collection_or_assertion_error(two_root_run) -> None:
    """The whole point: the operator must not see per-test failures."""
    combined = two_root_run.stdout + two_root_run.stderr
    assert "ModuleNotFoundError" not in combined, (
        "The guard must fire BEFORE the namespace capture produces import "
        f"errors.\n{combined}"
    )
    assert "data_collector" not in combined, (
        f"Refusal leaked the downstream symptom instead of the cause.\n{combined}"
    )


def test_refusal_message_names_both_roots(two_root_run) -> None:
    combined = two_root_run.stdout + two_root_run.stderr
    marker = "spans more than one test root"
    assert marker in combined, f"guard message absent\n{combined}"
    # Anchor on the guard's own message, not on incidental echoes of the
    # arguments elsewhere in pytest's output.
    message = combined[combined.index(marker):]
    assert "shared/tests" in message, message
    assert "integration-tests" in message, message


def test_refusal_message_gives_supported_command(two_root_run) -> None:
    """An actionable message names the way forward, not just the problem."""
    combined = two_root_run.stdout + two_root_run.stderr
    assert "one test root per" in combined.lower(), combined
    assert "junit" in combined.lower(), (
        "Producing one junit.xml is what drives operators to combine the "
        f"roots; the message must address it.\n{combined}"
    )


# --------------------------------------------------------------------------- #
# Behaviour: a single-root session is untouched (AC2)
# --------------------------------------------------------------------------- #


def test_single_root_session_is_untouched() -> None:
    result = _run_pytest("integration-tests/test_shared_contracts_consumers.py")
    assert result.returncode == 0, (
        f"Single-root collection must be unaffected.\n{result.stdout}\n{result.stderr}"
    )
    assert "one test root per" not in (result.stdout + result.stderr).lower()


def test_single_root_session_still_executes_green() -> None:
    """Collection alone is too weak for AC2 -- actually RUN the root.

    A guard that let collection through but perturbed execution (an
    autouse fixture, a mutated sys.path, a swallowed hook) would sail past
    a `--collect-only` check. This runs the very module that the namespace
    capture used to break and requires it green with a non-zero test count.
    """
    result = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q",
            "integration-tests/test_shared_contracts_consumers.py",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert "failed" not in result.stdout.lower(), result.stdout
    match = re.search(r"(\d+) passed", result.stdout)
    assert match and int(match.group(1)) > 0, (
        f"Expected a non-zero passing count.\n{result.stdout}"
    )


def test_multi_root_is_refused_from_a_subdirectory() -> None:
    """Relative args are relative to the INVOCATION dir, not the repo root.

    `cd shared && pytest tests ../integration-tests` is the same unsupported
    session. Resolving those args against the repo root instead would send
    both to paths that do not exist, match no root, and wave the session
    through -- straight back into the 21 misleading failures.
    """
    result = _run_pytest("tests", "../integration-tests", cwd=REPO_ROOT / "shared")
    assert result.returncode != 0, (
        "A two-root session launched from a subdirectory must still be "
        f"refused.\n{result.stdout[-2000:]}"
    )
    assert "spans more than one test root" in (result.stdout + result.stderr)


def test_no_argument_session_is_not_refused() -> None:
    """`uv run pytest` with no paths collects from `testpaths`.

    The arg-based hook sees whatever pytest put in `config.args`; this pins
    that the bare invocation still works, since it is the single most
    common command anyone types.
    """
    result = _run_pytest(cwd=REPO_ROOT)
    combined = result.stdout + result.stderr
    assert "spans more than one test root" not in combined, combined
    assert result.returncode == 0, combined[-2000:]


def test_collected_items_are_judged_as_well_as_the_arguments() -> None:
    """The backstop hook must be wired, not merely defined.

    `pytest_sessionstart` reads the command line and so cannot see targets
    pytest derives another way. `pytest_collection_modifyitems` judges what
    was actually collected. Drive it through a path that reaches two roots
    and require the refusal to name both.
    """
    result = _run_pytest("shared/tests/test_pytest_root_guard.py", "integration-tests")
    combined = result.stdout + result.stderr
    assert "spans more than one test root" in combined, combined


def test_conftest_colliding_pair_still_fails_loudly() -> None:
    """`shared/tests` + `shared/scripts/tests` never reach the guard.

    Both resolve to the module name `tests.conftest`, so pytest raises
    `ImportPathMismatchError` while loading conftests -- before
    `pytest_sessionstart` exists to refuse anything. That is acceptable
    (the error is loud and names both files) but it must not silently
    become a PASS, and the docs must not claim the guard covers it.
    """
    result = _run_pytest("shared/tests", "shared/scripts/tests")
    combined = result.stdout + result.stderr
    assert result.returncode != 0, combined[-2000:]
    assert (
        "ImportPathMismatchError" in combined
        or "spans more than one test root" in combined
    ), f"multi-root session neither refused nor loudly failed:\n{combined[-2000:]}"


def test_dot_inside_a_root_is_not_refused() -> None:
    """The guard's own worst failure would be refusing a NORMAL run.

    `cd shared/tests && pytest .` is one root. Resolving `.` against the
    repo root rather than the invocation dir would make it an ancestor of
    every root and block a command CI itself relies on.
    """
    result = _run_pytest(".", cwd=REPO_ROOT / "shared" / "tests")
    combined = result.stdout + result.stderr
    assert "spans more than one test root" not in combined, combined


