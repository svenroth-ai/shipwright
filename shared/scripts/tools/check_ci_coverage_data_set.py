#!/usr/bin/env python3
"""Fail closed when a coverage data file did not reach the gather job.

``ci.yml`` measures coverage in more than one job: the plugin and integration tiers in
``tests-main`` and the ``shared/`` tier in ``tests-shared``; each job's ``.cov-data/`` travels
to the gather job ``python-checks`` as an artifact. ``ci_junit_plan.py verify`` proves the JUnit reports
arrived; nothing proved the coverage data did. ``combine_coverage.py`` reports ``ok`` on
whatever arrived and ``Diff coverage (gate)`` is skipped when no ``coverage.xml`` exists, so
a dropped ``.coverage.<name>`` would leave that tier's changed lines ungated while the
required check stays green.

The expected set is derived from the repository the same way the CI test loop derives what
it measures — never a hand-maintained list:

* ``.coverage.shared`` — always (the three ``shared/`` roots append into it);
* ``.coverage.integration`` — when ``integration-tests/`` exists;
* ``.coverage.<name>`` — for every ``plugins/<name>/`` with ``pyproject.toml``, ``tests/``
  AND ``scripts/`` (a plugin without ``scripts/`` runs its tests but is not measured).

Exit 0 = every expected file is present and non-empty. Exit 1 = at least one is missing.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def expected_files(project_root: Path) -> list[str]:
    names = [".coverage.shared"]
    if (project_root / "integration-tests").is_dir():
        names.append(".coverage.integration")
    plugins = project_root / "plugins"
    if plugins.is_dir():
        for plugin in sorted(p for p in plugins.iterdir() if p.is_dir()):
            if (
                (plugin / "pyproject.toml").is_file()
                and (plugin / "tests").is_dir()
                and (plugin / "scripts").is_dir()
            ):
                names.append(f".coverage.{plugin.name}")
    return names


def missing_files(project_root: Path, data_dir: Path) -> list[str]:
    missing = []
    for name in expected_files(project_root):
        path = data_dir / name
        if not path.is_file() or path.stat().st_size == 0:
            missing.append(name)
    return missing


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-root", default=Path("."), type=Path)
    ap.add_argument("--data-dir", default=None, type=Path, help="default: <project-root>/.cov-data")
    args = ap.parse_args(argv)
    root = args.project_root.resolve()
    data_dir = (args.data_dir or root / ".cov-data").resolve()
    expected = expected_files(root)
    missing = missing_files(root, data_dir)
    if missing:
        print(
            f"ERROR: {len(missing)} of {len(expected)} coverage data file(s) missing or empty in "
            f"{data_dir}: {missing} - a test job's coverage did not reach the gather job, so "
            "those tiers' changed lines would pass the diff-coverage gate unmeasured.",
            file=sys.stderr,
        )
        return 1
    print(f"coverage data set complete: {len(expected)} file(s) in {data_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
