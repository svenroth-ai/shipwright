"""Where a triage write just landed — outbox vs tracked, reported not derived.

`triage.mark_status` / `amend_triage_item` already DERIVE the write target
(`should_route_to_outbox`'s branch+origin check, or item residence) but until
iterate-2026-09-12-triage-route-report neither said which one a given call
used. Three same-session flips (`trg-ff6ea5f0`/`trg-5ae23b62`/`trg-4fac93bf`)
landed tracked-on-a-freshly-created-branch instead of the outbox an idle-main
flip would have used, and each needed its own PR before the operator noticed
— `lib.triage_delivery` answers "has it been delivered?" after the fact, on a
read; nothing answered "where did my write just go?" at write time. This
module is the presentation layer for that answer — split out of
`triage_cli_commands.py` to keep that file under its own 300-LOC budget
(`shipwright_bloat_baseline.json`), not because the logic needs its own
abstraction otherwise.

Do NOT turn the derived target into a caller flag: `mark_status`'s own
docstring is explicit that the residence/branch derivation is deliberate
(data-loss reasoning). This module only reports what was already decided.
"""

from __future__ import annotations

from pathlib import Path

from lib.worktree_isolation import current_branch, default_branch


def route_label(to_outbox: bool) -> str:
    """The machine-readable route name for a JSON result payload."""
    return "outbox" if to_outbox else "tracked"


def route_note(project_root: Path, to_outbox: bool) -> str | None:
    """Human-facing note for where a status/amend write just landed.

    Outbox case reuses the wording `amend_triage_item`'s CLI caller already
    printed. Tracked case is the converse `amend` lacked too: a write that
    reached a branch, not `origin/<default>`, reaches main only with THAT
    branch's PR. Returns ``None`` when there's nothing to add (idle main,
    tracked target — the ordinary non-worktree case) or branch resolution
    fails (advisory only; never blocks the CLI result on a git error).
    """
    if to_outbox:
        return (
            "note: buffered in the local outbox, not yet on any branch — "
            "delivered on the next iterate's sweep"
        )
    try:
        branch = current_branch(project_root)
        default = default_branch(project_root)
    except Exception:  # noqa: BLE001 — advisory note, never block the CLI result
        return None
    if branch and branch != default:
        return (
            f"note: recorded on branch {branch!r}; it reaches {default} "
            "only with this branch's PR"
        )
    return None
