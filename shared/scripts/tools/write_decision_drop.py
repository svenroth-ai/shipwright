#!/usr/bin/env python3
"""Write one ADR to a per-run decision-drop file (iterate F3).

Since the unconditional-worktree refactor, iterate F3 no longer appends
directly to ``decision_log.md``. Two parallel iterates each running in their
own worktree would both compute ``max(existing ADR) + 1`` and claim the same
number — a silent collision discovered only at merge time.

Instead each iterate *drops* its ADR keyed by ``run_id`` (no number). The
sequential ``ADR-NNN`` is assigned at exactly one serialized point — the
``/shipwright-changelog`` release step — by ``aggregate_decisions.py``. This
mirrors the ``CHANGELOG-unreleased.d/`` drop pattern that already solved the
same race for changelog bullets.

The drop is JSON so ``aggregate_decisions.py`` can render it through the exact
same ``write_decision_log.format_entry()`` the direct-append path uses — zero
format drift between the two paths.

Filename: ``<run_id_sanitized>_<NNN>.json`` — ``NNN`` is the smallest unused
counter, claimed with ``O_EXCL`` so two ADRs from the same run never clobber.

CLI:
    uv run shared/scripts/tools/write_decision_drop.py \\
        --project-root . --run-id iterate-20260515-my-change \\
        --section "Iterate — change: my change" \\
        --title "Short title" \\
        --context "..." --decision "..." --consequences "..." \\
        [--rationale "..."] [--rejected "..."] \\
        [--architecture-impact component|data-flow|convention|none]
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
from datetime import date
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_main_repo_root  # noqa: E402
from lib.iterate_entry import sanitize_run_id_for_filename  # noqa: E402
from tools.write_decision_log import (  # noqa: E402
    ADR_SPEC_FOLDER,
    FieldLengthError,
    enforce_field_length_limits,
)

DROP_DIRNAME = "decision-drops"  # under .shipwright/agent_docs/
_ARCHITECTURE_IMPACTS = ("component", "data-flow", "convention", "none")
_MAX_COUNTER = 1000


class DecisionDropError(RuntimeError):
    """Raised when a decision-drop cannot be written."""


def drop_dir(project_root: Path) -> Path:
    """Resolve ``.shipwright/agent_docs/decision-drops/``, git-worktree-aware.

    Iterate F3 runs inside an ephemeral worktree (unconditional isolation).
    The worktree's drop dir is destroyed by ``git worktree remove`` before
    ``/shipwright-changelog``'s ``aggregate_decisions.py`` can fold the drop
    into ``decision_log.md`` — so the drop MUST be written next to the MAIN
    repo, the directory the aggregator reads. In a plain checkout (or when
    git is unavailable) this is identical to
    ``project_root/.shipwright/agent_docs/decision-drops`` — behavior
    unchanged. Mirrors ``lib.events_log.resolve_events_path``; kept in lock
    step with ``aggregate_decisions.drop_dir`` (drift = silently lost ADRs).
    """
    project_root = Path(project_root)
    root = resolve_main_repo_root(project_root) or project_root
    return root / ".shipwright" / "agent_docs" / DROP_DIRNAME


def _atomic_exclusive_write(target: Path, content: str) -> None:
    """Create ``target`` exclusively (O_EXCL) and write ``content``.

    Two callers racing for the same counter produce a deterministic result:
    exactly one wins, the loser gets ``FileExistsError`` and retries the next
    counter. Mirrors ``write_changelog_drop._atomic_exclusive_write``.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    fd = os.open(target, flags, 0o644)
    try:
        with os.fdopen(fd, "wb", closefd=True) as fh:
            fh.write(content.encode("utf-8"))
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(target)
        raise


def write_decision_drop(
    project_root: Path,
    *,
    run_id: str,
    section: str,
    title: str,
    context: str,
    decision: str,
    consequences: str,
    rationale: str = "",
    rejected: str = "",
    commit: str = "",
    architecture_impact: str = "none",
    spec_ref: str = "",
) -> Path:
    """Write one ADR decision-drop. Returns the absolute path written.

    Iterate A.3 hardens this path: each of context / decision / consequences /
    rationale / rejected must be within ``ADR_FIELD_MAX_CHARS``. Long-form
    prose belongs in ``spec_ref`` → ``.shipwright/planning/adr/<NNN>-<slug>.md``.
    """
    if not run_id.strip():
        raise DecisionDropError("run_id is empty")
    if not decision.strip():
        raise DecisionDropError("decision is empty")
    if architecture_impact not in _ARCHITECTURE_IMPACTS:
        raise DecisionDropError(
            f"unknown architecture_impact {architecture_impact!r}. "
            f"Allowed: {list(_ARCHITECTURE_IMPACTS)}"
        )

    try:
        enforce_field_length_limits(
            context=context, decision=decision, consequences=consequences,
            rationale=rationale, rejected=rejected,
        )
    except FieldLengthError as exc:
        raise DecisionDropError(str(exc)) from exc

    project_root = Path(project_root).resolve()
    payload = {
        "run_id": run_id,
        "date": date.today().isoformat(),
        "section": section,
        "title": title,
        "context": context,
        "decision": decision,
        "consequences": consequences,
        "rationale": rationale,
        "rejected": rejected,
        "commit": commit,
        "architecture_impact": architecture_impact,
        "spec_ref": spec_ref,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"

    dd = drop_dir(project_root)
    safe = sanitize_run_id_for_filename(run_id)
    for counter in range(1, _MAX_COUNTER):
        candidate = dd / f"{safe}_{counter:03d}.json"
        try:
            _atomic_exclusive_write(candidate, text)
            return candidate
        except FileExistsError:
            continue
    raise DecisionDropError(
        f"too many decision-drops for run_id={run_id} (counter overflow)"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Write one ADR decision-drop for iterate F3.",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--section", required=True, help="Section reference")
    parser.add_argument("--title", required=True, help="Short ADR title")
    parser.add_argument("--context", required=True)
    parser.add_argument("--decision", required=True)
    parser.add_argument("--consequences", required=True)
    parser.add_argument("--rationale", default="")
    parser.add_argument("--rejected", default="", help="Rejected alternatives")
    parser.add_argument(
        "--commit",
        default="",
        help="Commit hash if known (usually unknown at F3 — left blank)",
    )
    parser.add_argument(
        "--architecture-impact",
        default="none",
        choices=list(_ARCHITECTURE_IMPACTS),
    )
    parser.add_argument(
        "--spec-ref",
        default="",
        help=(
            "Optional path (relative to project root) to long-form ADR spec — "
            f"convention: {ADR_SPEC_FOLDER}/<NNN>-<slug>.md (flat, one file "
            "per ADR). Rendered as a `**Details:** [...]` link in the "
            "aggregated decision_log.md."
        ),
    )
    args = parser.parse_args(argv)

    try:
        path = write_decision_drop(
            Path(args.project_root),
            run_id=args.run_id,
            section=args.section,
            title=args.title,
            context=args.context,
            decision=args.decision,
            consequences=args.consequences,
            rationale=args.rationale,
            rejected=args.rejected,
            commit=args.commit,
            architecture_impact=args.architecture_impact,
            spec_ref=args.spec_ref,
        )
    except DecisionDropError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # The drop is written next to the MAIN repo (worktree-aware drop_dir),
    # which is ABOVE --project-root when F3 runs inside an iterate worktree —
    # `relative_to` would then raise ValueError. Show the path relative to
    # --project-root when it is genuinely below it, else the absolute path.
    try:
        display = path.relative_to(Path(args.project_root).resolve())
    except ValueError:
        display = path
    print(str(display))
    print(
        f"decision-drop written for run_id={args.run_id} — ADR-NNN assigned "
        "at /shipwright-changelog release time.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
