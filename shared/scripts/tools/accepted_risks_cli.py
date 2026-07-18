#!/usr/bin/env python3
"""Reconcile the accepted-risk register against the suppressions actually in place.

The register (``shipwright_accepted_risks.yaml``) is the human-authored RECORD;
the scanner wiring (``.trivyignore*``, the ``SHIPWRIGHT_SEMGREP_*`` env vars in
``security.yml``) is what actually suppresses. Keeping them as two files only
works if something proves they agree — otherwise the register is documentation
that drifts, which is the failure mode it was built to end.

Three subcommands; the two offline ones are read-only:

``check``    both directions. A suppression with no register entry is an
             UNRECORDED acceptance (nobody knows why it is there or when to
             re-review it). A register entry with no suppression is a STALE
             record (it claims something is accepted that no longer is).
``expire``   fails when an acceptance is past its re-review date.
``converge`` resolves ``github-dismissal`` entries against LIVE GitHub
             code-scanning state. Read-only unless ``--apply`` is passed.

Both are wired into ``shared/tests/test_accepted_risks_register.py`` so they run
on the path CI already requires. A gate nothing invokes constrains nothing — the
external review caught exactly that in this iterate's first draft.

**``github-dismissal`` entries are NOT checked by ``check``** and are reported
as unchecked there. Their counterpart is live GitHub alert state, not a file, so
the offline gate cannot see them — ``converge`` is where they are resolved.
Printing what was skipped is deliberate — a gate that silently narrows its own
scope reads as "all clear".

``converge`` is NOT wired into CI, and that is the design, not an omission. No
scheduled job may hold the authority to mass-dismiss security alerts; an
automated reconciler is the shape that produced webui #285. CI's job is to fail
when register and reality disagree — which ``check`` and ``expire`` already do.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from accepted_risks import (  # noqa: E402
    STATIC_TARGETS,
    RegisterError,
    load_register,
    register_exists,
    today_utc,
)
from github_code_scanning import RepoIdentityError  # noqa: E402
from accepted_risk_scan import (  # noqa: E402
    ACCEPT_GH_ACTION_TAGS_ENV,
    EXCLUDE_RULES_ENV,
    SECURITY_WORKFLOW_REL,
    TRIVYIGNORE_FLAT_NAME,
    TRIVYIGNORE_YAML_NAMES,
    discovered_suppressions,
    read_trivyignore_ids,
    read_workflow_env,
)

# The discovery readers live in the shared LEAF module ``accepted_risk_scan`` so
# the compliance dashboard can reuse them by bare module name, instead of this
# ``tools`` package having to be importable from inside a plugin (ADR-044/045).
# Re-exported here so callers and tests of this CLI are unaffected.
__all__ = [
    "ACCEPT_GH_ACTION_TAGS_ENV", "EXCLUDE_RULES_ENV", "SECURITY_WORKFLOW_REL",
    "TRIVYIGNORE_FLAT_NAME", "TRIVYIGNORE_YAML_NAMES", "discovered_suppressions",
    "read_trivyignore_ids", "read_workflow_env", "reconcile", "main",
]


def reconcile(project_root: Path | str) -> dict:
    """Both-directions comparison of register vs reality."""
    entries = load_register(project_root)
    discovered = discovered_suppressions(project_root)

    registered: dict[str, set[str]] = {t: set() for t in STATIC_TARGETS}
    unchecked: list = []
    for entry in entries:
        if entry.statically_checkable:
            registered[entry.target].add(entry.rule)
        else:
            unchecked.append(entry)

    unrecorded: list[tuple[str, str]] = []
    stale: list[tuple[str, str]] = []
    for target in STATIC_TARGETS:
        for rule in sorted(discovered[target] - registered[target]):
            unrecorded.append((target, rule))
        for rule in sorted(registered[target] - discovered[target]):
            stale.append((target, rule))

    return {
        "entries": entries,
        "unrecorded": unrecorded,
        "stale": stale,
        "unchecked": unchecked,
        "ok": not unrecorded and not stale,
    }


def _format_check(result: dict) -> list[str]:
    lines: list[str] = []
    for target, rule in result["unrecorded"]:
        lines.append(
            f"UNRECORDED  {target}: {rule}\n"
            "    A suppression is active with no register entry. Nobody can tell "
            "why it is accepted or when to re-review it.\n"
            f"    Fix: add an entry to shipwright_accepted_risks.yaml, or remove "
            "the suppression."
        )
    for target, rule in result["stale"]:
        lines.append(
            f"STALE       {target}: {rule}\n"
            "    The register claims this is accepted, but no such suppression "
            "is in place.\n"
            "    Fix: remove the register entry, or restore the suppression."
        )
    return lines


def cmd_check(project_root: Path) -> int:
    if not register_exists(project_root):
        print(
            f"accepted-risks: no register at {project_root} - nothing to reconcile.\n"
            "  (An absent register is a legacy/fresh repo, not an error.)"
        )
        return 0
    result = reconcile(project_root)

    n_checked = sum(len(v) for v in discovered_suppressions(project_root).values())
    print(
        f"accepted-risks check: {len(result['entries'])} register entr"
        f"{'y' if len(result['entries']) == 1 else 'ies'}, "
        f"{n_checked} source-controlled suppression(s) reconciled."
    )
    # Never let "not checkable offline" read as "checked and clean".
    for entry in result["unchecked"]:
        print(
            f"  UNCHECKED  {entry.target}: {entry.rule} ({entry.id}) - "
            "counterpart is live GitHub state, not a file. Resolve it with: "
            "accepted_risks_cli.py converge --project-root ."
        )

    problems = _format_check(result)
    if problems:
        print("\nAccepted-risk register drift:\n")
        for problem in problems:
            print(problem)
        return 1
    print("  no drift.")
    return 0


def cmd_expire(project_root: Path) -> int:
    if not register_exists(project_root):
        print(f"accepted-risks: no register at {project_root}.")
        return 0
    entries = load_register(project_root)
    now = today_utc()
    overdue = [e for e in entries if e.is_expired(now)]
    if not overdue:
        print(f"accepted-risks expire: {len(entries)} entries, none past due ({now}).")
        return 0
    print(f"Accepted risks past their re-review date (today {now} UTC):\n")
    for entry in overdue:
        print(
            f"EXPIRED  {entry.id}  (due {entry.expires}, ref {entry.rationale_ref})\n"
            f"    {entry.statement[:200]}\n"
            "    Re-review: fix it, or renew `expires` with a fresh rationale."
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconcile the accepted-risk register against real suppressions."
    )
    parser.add_argument(
        "command", choices=("check", "expire", "converge"),
        help="check drift / check expiry / converge the live security surface",
    )
    parser.add_argument("--project-root", default=".", help="repo root")
    parser.add_argument(
        "--apply", action="store_true",
        help="converge only: actually dismiss/reopen. Dry-run is the default, "
             "and no scheduled job may hold this authority.",
    )
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    try:
        if args.command == "check":
            return cmd_check(project_root)
        if args.command == "converge":
            # Imported lazily: `check`/`expire` are offline gates that run in
            # CI, and must not acquire a `gh`-shaped import at module load.
            from tools.accepted_risks_converge import (  # noqa: PLC0415
                cmd_converge,
            )
            return cmd_converge(project_root, apply=args.apply)
        return cmd_expire(project_root)
    except RegisterError as exc:
        # Fail closed: an unreadable register is never "no acceptances".
        print(f"accepted-risks: register is invalid - {exc}", file=sys.stderr)
        return 2
    except RepoIdentityError as exc:
        # Fail closed: an unresolvable repo or an incomplete listing is never
        # "converged" — that is precisely the reading that licenses inaction.
        print(f"accepted-risks: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
