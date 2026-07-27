"""Repo-root pytest guard: one test root per session.

This repository has several test roots, and each one needs the top-level
names ``scripts`` / ``lib`` / ``tools`` to mean a DIFFERENT directory:

* ``shared/tests`` -- pytest's prepend import mode puts ``<repo>/shared`` on
  ``sys.path`` (because ``shared/tests/__init__.py`` exists and
  ``shared/__init__.py`` does not), so ``scripts.*`` means ``shared/scripts``.
* ``integration-tests`` -- ``shared/contracts/compliance.py`` prepends the
  shipwright-compliance plugin root, so ``scripts.*`` must mean that
  plugin's tree.
* ``plugins/<name>/tests`` -- each plugin owns its own ``scripts``/``lib``/
  ``tools`` (ADR-044, the ``cross_plugin`` marker).

Those requirements are mutually exclusive within one process, and not by
sys.path ordering: ``shared/scripts/lib/__init__.py`` and
``plugins/*/scripts/lib/__init__.py`` are REGULAR packages, so whichever is
imported first is cached in ``sys.modules`` and never re-resolves. A later
``sys.path.insert(0, ...)`` is powerless against it.

`.github/workflows/ci.yml` therefore runs one root per pytest process. The
failure mode this guard removes is what happens when that rule is broken by
hand: 21 tests fail inside `integration-tests/test_shared_contracts_*` with
`ModuleNotFoundError: No module named 'scripts.lib.data_collector'`, naming
files the change under test never touched and reading as a fresh
regression. Refusing the session states the real cause once, up front.

The guard is pure: no fixtures, no test mutation. A session that touches
zero or one test root is untouched.

Two limits, stated because a guard trusted beyond its reach is worse than
no guard:

1. It only runs when the repo root is the pytest rootdir. Every plugin
   carries its own ``[tool.pytest.ini_options]``, so ``cd plugins/<name> &&
   pytest tests/`` roots there and never loads this file (verified: the
   repo root is absent from ``sys.path`` in such a session). A multi-root
   session launched that way is caught later, by the capture check in
   ``shared/contracts/compliance.py``.
2. Some root pairs collide even earlier, while pytest imports their
   conftests -- ``shared/tests`` and ``shared/scripts/tests`` both resolve
   to the module name ``tests.conftest`` and raise
   ``ImportPathMismatchError`` before ``pytest_sessionstart`` runs. That
   failure is ugly but it is loud and it names both files, which is the
   property that matters; it is not the silent-wrong-modules case this
   guard exists for.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent

# Directory names discovery never descends into. The walk starts at
# `shared/` and `plugins/`, so only names reachable from there are listed --
# a longer list would be dead config that reads as protection.
#
# `.venv` / `venv` / `node_modules` are the ones that matter: a plugin
# virtualenv contains third-party packages with `tests/` directories of
# their own, and treating one as a repo test root would refuse an ordinary
# single-root session. `__pycache__` and the caches are pruned for speed --
# this walk runs at EVERY pytest start.
_SKIP_DIRS = {
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".tox",
}


def discover_test_roots(repo_root: Path) -> set[Path]:
    """Return every directory that owns its own top-level import namespace.

    Discovered, not hard-coded, so a new plugin or a new ``shared/**/tests``
    directory cannot silently fall outside the guard while CI keeps running
    it as its own pytest process.

    Only OUTERMOST ``tests`` directories count. Several roots carry fixture
    repositories that contain a ``tests`` directory of their own (e.g.
    ``plugins/*/tests/fixtures/mini_repos/app/tests``). Those are data, not
    import namespaces -- counting them would make the guard refuse a
    perfectly ordinary single-root run.
    """
    found: set[Path] = set()

    integration = repo_root / "integration-tests"
    if integration.is_dir():
        found.add(integration)

    for parent in (repo_root / "shared", repo_root / "plugins"):
        if parent.is_dir():
            _walk_for_tests(parent, found)

    # Keep only the OUTERMOST roots.
    return {root for root in found if not found & set(root.parents)}


def _walk_for_tests(start: Path, found: set[Path]) -> None:
    """Collect ``tests`` directories under ``start``, pruning as we go.

    Pruning rather than filtering afterwards is deliberate: a filtered
    ``rglob`` still walks every file in ``plugins/*/.venv`` before throwing
    the results away, on every single pytest start.
    """
    try:
        entries = list(start.iterdir())
    except OSError:  # pragma: no cover -- unreadable dir
        return
    for entry in entries:
        if not entry.is_dir() or entry.is_symlink():
            continue
        if entry.name in _SKIP_DIRS:
            continue
        if entry.name == "tests":
            found.add(entry)
            continue  # nothing inside a root is a separate root
        _walk_for_tests(entry, found)


def resolve_test_roots(args, repo_root: Path, invocation_dir: Path | None = None) -> set[Path]:
    """Map pytest's path arguments onto the test roots they reach.

    An argument may carry a ``::node-id`` selector, may sit inside a root,
    or may be an ANCESTOR of several roots -- ``pytest .`` from the repo
    root spans every one of them, which is the same unsupported session
    written a shorter way.

    ``invocation_dir`` is the directory pytest was invoked from, which is
    what relative arguments are relative to -- NOT the repo root. Resolving
    against the repo root instead would let ``cd shared && pytest tests
    ../integration-tests`` slip past the guard: both arguments would land on
    paths that do not exist, reach no root, and the session would proceed
    straight into the failure this guard exists to prevent.
    """
    base = invocation_dir or repo_root
    known = discover_test_roots(repo_root)
    reached: set[Path] = set()

    for raw in args:
        path_part = str(raw).split("::", 1)[0].strip()
        if not path_part:
            continue
        candidate = Path(path_part)
        if not candidate.is_absolute():
            candidate = base / candidate
        try:
            candidate = candidate.resolve()
        except OSError:  # pragma: no cover -- defensive
            continue

        for root in known:
            if candidate == root or root in candidate.parents:
                reached.add(root)  # arg is the root, or lives inside it
            elif candidate in root.parents:
                reached.add(root)  # arg is an ancestor that contains the root

    return reached


def _format_refusal(roots: set[Path], repo_root: Path) -> str:
    """Name every colliding root, and give a command for every one of them.

    A session can span more than two roots (`pytest .` spans them all), and
    a recipe that silently covered only the first two would leave the
    operator to guess the rest -- the same "figure it out yourself" failure
    this guard exists to remove.
    """
    listed = sorted(r.relative_to(repo_root).as_posix() for r in roots)
    bullets = "\n".join(f"    - {name}" for name in listed)
    separate = "\n".join(
        f'    uv run pytest {name} -m "not slow and not cross_plugin"' for name in listed
    )
    junit = "\n".join(
        f"    uv run pytest {name} "
        f"--junitxml=.shipwright/runs/<run_id>/junit-{i}.xml"
        for i, name in enumerate(listed, start=1)
    )
    return (
        "This pytest session spans more than one test root:\n"
        f"{bullets}\n"
        "\n"
        "Shipwright supports exactly one test root per pytest process.\n"
        "Each root needs the top-level names `scripts` / `lib` / `tools` to\n"
        "resolve to a different directory, and Python caches a regular\n"
        "package the first time it is imported -- so the second root in a\n"
        "shared process silently gets the first root's modules. No sys.path\n"
        "ordering can undo that (ADR-044, the `cross_plugin` marker).\n"
        "\n"
        "Run them as separate invocations instead:\n"
        f"{separate}\n"
        "\n"
        "Collecting junit evidence? Write one file per root and keep them all\n"
        "-- one process cannot emit a single junit.xml spanning roots. If you\n"
        "need one artifact, merge them afterwards; `combine_coverage.py` does\n"
        "exactly this for per-root coverage data:\n"
        f"{junit}\n"
    )


def roots_containing(paths, repo_root: Path) -> set[Path]:
    """Return the known roots that these already-resolved paths live under.

    No parsing: the caller supplies real filesystem paths.
    """
    known = discover_test_roots(repo_root)
    reached: set[Path] = set()
    for path in paths:
        resolved = Path(path).resolve()
        for root in known:
            if resolved == root or root in resolved.parents:
                reached.add(root)
    return reached


def pytest_sessionstart(session: pytest.Session) -> None:
    """Refuse a multi-root session BEFORE any test module is imported.

    This is the only phase that runs ahead of every import, which is what
    the guard needs: some cross-root collisions blow up during collection,
    not during the run, and by then the misleading errors have already been
    printed. It works from the raw arguments, so `pytest_collection_modifyitems`
    below backstops it with pytest's own authoritative resolution.
    """
    roots = resolve_test_roots(
        session.config.args,
        _REPO_ROOT,
        Path(session.config.invocation_params.dir),
    )
    if len(roots) > 1:
        raise pytest.UsageError(_format_refusal(roots, _REPO_ROOT))


def pytest_collection_modifyitems(session: pytest.Session, config, items) -> None:
    """Backstop: judge what pytest ACTUALLY collected, before anything runs.

    `pytest_sessionstart` reads the command line, so it cannot see targets
    that pytest derives by other means -- `testpaths`, `--pyargs`, a
    `-k`/`--deselect` driven selection, or a future config mechanism. Here
    the collected items are already resolved by pytest itself, so no
    argument parsing is involved and nothing has executed yet.

    Both hooks are kept: this one cannot replace the first, because a
    collision that fails at COLLECTION time has already surfaced by the
    time collection finishes.
    """
    roots = roots_containing((item.path for item in items), _REPO_ROOT)
    if len(roots) > 1:
        raise pytest.UsageError(_format_refusal(roots, _REPO_ROOT))
