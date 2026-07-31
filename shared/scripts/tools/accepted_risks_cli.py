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
from datetime import date
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from accepted_risks import (  # noqa: E402
    STATIC_TARGETS,
    TARGET_TRIVY_IGNORE,
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


def _ignore_file_exists(project_root: Path | str) -> bool:
    """Whether ANY Trivy ignore-file form is present on disk.

    Distinguishes "no ignore file" from "an ignore file that yielded nothing",
    which the reader reports identically as an empty set.
    """
    root = Path(project_root)
    names = (*TRIVYIGNORE_YAML_NAMES, TRIVYIGNORE_FLAT_NAME)
    return any((root / name).is_file() for name in names)


def reconcile(project_root: Path | str) -> dict:
    """Both-directions comparison of register vs reality.

    An ABSENT register reconciles as an empty one rather than being skipped:
    ``load_register`` already returns ``[]`` for it, and the question this gate
    asks is "is every live suppression recorded?", never "does a file exist?".
    """
    entries = load_register(project_root)
    discovered = discovered_suppressions(project_root)

    # `date.min` predates every date a repo would realistically write, so the
    # expiry filter drops nothing: this is every id in the ignore file, lapsed
    # or not. Subtracting the live ones leaves the lapsed ones. A stale record
    # has three very different causes needing different advice — see
    # `_format_check`; `ignore_unreadable` separates the third from the others.
    written_down = read_trivyignore_ids(project_root, now=date.min)
    lapsed = written_down - discovered[TARGET_TRIVY_IGNORE]
    ignore_unreadable = _ignore_file_exists(project_root) and not written_down

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
        "discovered": discovered,
        "lapsed": lapsed,
        "ignore_unreadable": ignore_unreadable,
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
        if target == TARGET_TRIVY_IGNORE and result.get("ignore_unreadable"):
            # THIRD cause, and the most destructive one to get wrong: the ignore
            # file is there but yielded nothing, so it probably does not parse.
            # The reader reports that identically to "no suppressions", which
            # would otherwise print remove-the-record for every Trivy acceptance
            # in the register — deleting real records over a YAML typo.
            lines.append(
                f"STALE       {target}: {rule}\n"
                "    An ignore file is present but yielded NO entries — it most "
                "likely does not parse. Nothing can be concluded about this "
                "record until that is fixed.\n"
                "    Fix: check the ignore file's syntax first. Do NOT remove "
                "register entries on the strength of this line."
            )
            continue
        if target == TARGET_TRIVY_IGNORE and rule in result.get("lapsed", ()):
            # The entry IS still in the ignore file — its own due date has
            # passed, so the scanner has stopped applying it. Telling the
            # operator to "remove the register entry" here would delete an
            # acceptance that is doing its job, which is the exact outcome
            # `_is_lapsed`'s fail-safe exists to avoid. This is not a corner
            # case: a register `expires` and an ignore `expired_at` set to the
            # SAME day lapse a day apart (the register is active ON its date,
            # Trivy's entry is not), so a diligently paired acceptance lands
            # here for one day at every renewal.
            lines.append(
                f"STALE       {target}: {rule}\n"
                "    The register claims this is accepted, and the ignore entry "
                "is still in the file — but its own expiry (expired_at: / exp:) "
                "has passed, so the scanner already stopped suppressing it.\n"
                "    Fix: renew BOTH dates (the ignore entry's and the "
                "register's), or remove both. Note they lapse a day apart: an "
                "ignore entry expires ON its date, a register entry AFTER its."
            )
            continue
        lines.append(
            f"STALE       {target}: {rule}\n"
            "    The register claims this is accepted, but no such suppression "
            "is in place.\n"
            "    Fix: remove the register entry, or restore the suppression."
        )
    return lines


def cmd_check(project_root: Path) -> int:
    result = reconcile(project_root)
    n_entries = len(result["entries"])
    n_checked = sum(len(v) for v in result["discovered"].values())

    if register_exists(project_root):
        print(
            f"accepted-risks check: {n_entries} register entr"
            f"{'y' if n_entries == 1 else 'ies'}, "
            f"{n_checked} source-controlled suppression(s) reconciled."
        )
    else:
        # Reconciled anyway. Returning success on the missing FILE — as this
        # gate used to, before discovering anything — meant deleting the
        # register silenced it while every suppression it recorded stayed live.
        # A fresh repo still passes, because it suppresses nothing; it now does
        # so by comparison rather than by exemption
        # (iterate-2026-07-31-accepted-risk-gate-holes).
        print(
            f"accepted-risks check: no register at {project_root} - "
            f"reconciling {n_checked} source-controlled suppression(s) "
            "against an empty record."
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
