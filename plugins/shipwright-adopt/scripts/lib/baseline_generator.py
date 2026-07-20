"""Adopt-onboarding wrapper around ``bloat_baseline.scan``.

Called as the **first** artifact-writing step of ``/shipwright-adopt``
(Step A.0 — see ``plugins/shipwright-adopt/skills/adopt/SKILL.md``) so
that ``shipwright_bloat_baseline.json`` exists in the target repo
BEFORE Adopt writes any over-limit artefact (CLAUDE.md, decision_log.md,
architecture.md, …) and BEFORE the Stop-Gate hook can fire on the first
Stop event of the Adopt session.

Idempotent: re-runs overwrite atomically. Safe to call from CLI or
from the SKILL.md flow.

Import of ``shared/scripts/lib/bloat_baseline.py`` uses the pollution-
free ``spec_from_file_location`` loader (ADR-045) — a plain
``from lib import bloat_baseline`` would pin the ``lib`` namespace to
``shared/scripts/lib`` and shadow the adopt plugin's own ``lib/`` for
the rest of the test session.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:  # tool context: lib/ is on sys.path (setup_adopt/_load_lib)
    from shared_loader import load_shared_module
except ImportError:  # test / package context: scripts/ on sys.path, lib is a package
    from lib.shared_loader import load_shared_module

_bb = load_shared_module(
    "scripts/lib/bloat_baseline.py", "_shipwright_adopt_bloat_baseline"
)


def generate(project_root: Path | str) -> Path:
    """Scan ``project_root`` and write ``shipwright_bloat_baseline.json``.

    Returns the absolute path of the written file. Always writes,
    even when no entries are oversize — an empty baseline is a valid
    "this project is currently clean" signal that distinguishes
    pre-adopt state from "I have explicitly checked and there's
    nothing to grandfather".
    """
    root = Path(project_root)
    entries = _bb.scan(root)
    doc = {"version": 1, "entries": entries}
    return _bb.write_baseline(root, doc)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: ``uv run baseline_generator.py [--project-root <p>]``."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate the bloat baseline")
    parser.add_argument("--project-root", default=".")
    args = parser.parse_args(argv)
    target = generate(args.project_root)
    print(str(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
