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

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_bloat_baseline() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[4]
    file_path = repo_root / "shared" / "scripts" / "lib" / "bloat_baseline.py"
    sentinel = "_shipwright_adopt_bloat_baseline"
    if sentinel in sys.modules:
        return sys.modules[sentinel]
    spec = importlib.util.spec_from_file_location(sentinel, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load spec for {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[sentinel] = module
    spec.loader.exec_module(module)
    return module


_bb = _load_bloat_baseline()


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
