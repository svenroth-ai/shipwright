#!/usr/bin/env python3
"""Verify every file a build section changed is accounted for by that section.

Part (3) of the requirement write-back loop. A section that cannot be built
without touching something shared MAY make the smallest change it needs — but it
must be *recorded as belonging to that section*. This is the check that makes
that recording real: every added or modified path in the section's commit range
must be either declared in the section's ``## Files to Create/Modify`` block or
carried as an attributed extra on its requirement-impact declaration.

Usage::

    uv run check_section_file_attribution.py --project-root . \\
      --section-file .shipwright/planning/03-auth/sections/01-auth.md \\
      --run-id "$RUN" --scope 01-auth --base-ref main --head-ref HEAD

Exit codes: ``0`` attributed (or unverifiable — see below), ``1`` unattributed
files found, ``2`` the request itself was bad.

**Deletions and renames are reported, not failed.** A section file lists what it
creates and modifies; it does not list what it removes, so counting a deletion as
unattributed would fail correct sections. They are surfaced so a reviewer can see
them.

**Framework bookkeeping is excluded, and the exclusion is stated.** The phase
commits with ``git add -A`` and then writes tracked artifacts at Steps 9/10/10b —
the event log, the decision log, the build config, this mechanism's own
declaration — so the NEXT section's commit sweeps them up. An earlier version of
this tool claimed the Step-10b ordering made that impossible; it does not, and
relying on it would have false-failed every section after the first. The real
rule is :data:`section_file_list.FRAMEWORK_BOOKKEEPING`: artifacts the phase
itself is required to write are not section work and are not attributable.
Everything outside that list is still the section's to declare.

**Scope the range to the section's own commit** (``--base-ref HEAD^ --head-ref
HEAD`` immediately after the Step 8 commit). Passing the branch base instead puts
every earlier section on the branch inside this section's range.

Origin: trg-e9e5188e (FR-01.05).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]  # shared/scripts
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.fr_classification import is_behavior_affecting  # noqa: E402
from lib.requirement_impact import is_requirement_spec  # noqa: E402
from lib.requirement_impact_git import (  # noqa: E402
    SOURCE_ERROR,
    SOURCE_GIT,
    changed_paths,
)
from lib.requirement_impact_store import (  # noqa: E402
    declaration_dir,
    find_declaration,
)
from lib.section_file_list import (  # noqa: E402
    parse_declared_files,
    unattributed_paths,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check a build section's changed files are attributed to it",
    )
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--section-file", required=True,
                        help="the section plan whose ## Files to Create/Modify block declares scope")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--scope", required=True, help="the section name")
    parser.add_argument("--base-ref", required=True)
    parser.add_argument("--head-ref", required=True)
    return parser


def _emit(payload: dict, code: int) -> int:
    print(json.dumps(payload, indent=2))
    return code


def _auto_attributed_specs(declaration, evidence) -> list[str]:
    """Requirement specs this declaration itself accounts for — or nothing.

    Three conditions, all required. The declaration must be behaviour-affecting
    (an ``--impact none`` section editing requirements is a real divergence and
    stays reported); its touch check must actually have RUN (``source == "git"``,
    not a skipped one); and it must have verified **this** range — otherwise a
    declaration recorded over a broad or older range containing some spec edit
    would attribute an unrelated spec change in a later section. The recorder
    stores the resolved SHAs precisely so this consumer can insist on that.

    Paths are re-filtered through ``is_requirement_spec`` because the declaration
    is a hand-editable file on disk: without it, listing ``src/anything.py`` under
    ``touch_check.spec_files`` would attribute that file with no reason at all —
    weaker than the ``--extra`` path it bypasses.
    """
    if not is_behavior_affecting((declaration or {}).get("impact")):
        return []
    touch = (declaration or {}).get("touch_check") or {}
    if touch.get("source") != SOURCE_GIT:
        return []
    if (touch.get("base_sha") != evidence.get("base_sha")
            or touch.get("head_sha") != evidence.get("head_sha")):
        return []
    return [p for p in (touch.get("spec_files") or []) if is_requirement_spec(p)]


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    project_root = Path(args.project_root).resolve()

    section_path = Path(args.section_file)
    if not section_path.is_absolute():
        section_path = project_root / section_path
    try:
        section_text = section_path.read_text(encoding="utf-8")
    except OSError as exc:
        return _emit({"success": False, "error": "section_file_unreadable",
                      "detail": str(exc)}, 2)

    evidence = changed_paths(project_root,
                             base_ref=args.base_ref, head_ref=args.head_ref)
    if evidence["source"] == SOURCE_ERROR:
        return _emit({"success": False, "error": "evidence_unusable",
                      "detail": evidence["detail"]}, 2)
    if evidence["source"] != SOURCE_GIT:
        # No git, no repository — unverifiable, not a violation. Said out loud so
        # a green result is never mistaken for a check that ran.
        return _emit({"success": True, "status": "skipped",
                      "detail": evidence["detail"]}, 0)

    declaration, problems = find_declaration(
        declaration_dir(project_root),
        run_id=args.run_id, phase="build", scope=args.scope,
    )
    if problems:
        # A damaged record is not a missing one. Reporting everything as
        # unattributed here would send the operator to write attributions when
        # the actual remedy is to repair the file.
        return _emit({"success": False, "error": "declaration_damaged",
                      "detail": "repair these declaration files before re-running",
                      "problems": problems}, 2)

    extras = (declaration or {}).get("extras") or []
    # A section that resolved a mockup-vs-spec contradiction is REQUIRED to
    # correct the requirement, so its spec.md edit is a mandated output — already
    # recorded, and more strongly than an extra: the declaration names the FR and
    # its touch check git-verified the file. Passed only when the declaration is
    # behaviour-affecting, so an `--impact none` section that edits requirements
    # anyway is still reported. Re-filtered through `is_requirement_spec` because
    # the file is on disk and hand-editable: without it, listing `src/anything.py`
    # under `touch_check.spec_files` would attribute that file with no reason at
    # all — weaker than the `--extra` path it bypasses.
    verified_specs = _auto_attributed_specs(declaration, evidence)

    declared = parse_declared_files(section_text)
    missing = unattributed_paths(
        evidence["added_modified"], declared=declared, extras=extras,
        requirement_specs=verified_specs)
    # A DELETION outside the section's scope is out-of-scope work too — arguably
    # the most destructive kind. An earlier version reported every deletion and
    # failed none, so `git rm shared/lib/legacy_client.py` passed clean. What a
    # section file genuinely does not list is the removal of a file it DID
    # declare, so only undeclared deletions fail.
    missing_deletions = unattributed_paths(
        evidence["deleted"], declared=declared, extras=extras,
        requirement_specs=verified_specs)
    failed = bool(missing or missing_deletions or declaration is None)

    payload = {
        "success": not failed,
        "section": args.scope,
        "range": evidence["detail"],
        "declared_files": declared,
        "attributed_extras": [e.get("path") for e in extras if isinstance(e, dict)],
        "unattributed": missing,
        "unattributed_deletions": missing_deletions,
        "deleted": evidence["deleted"],
        "renamed": evidence["renamed"],
        "declaration_found": declaration is not None,
    }
    details: list[str] = []
    if declaration is None:
        # Without this the build side had no equivalent of the design gate: a
        # section that skipped the recorder entirely still exited 0 as long as
        # its diff happened to sit inside its declared block.
        details.append(
            f"section {args.scope!r} recorded no requirement-impact declaration "
            f"for run {args.run_id!r} — run record_requirement_impact.py "
            "--phase build first. Declaring 'none' with a reason is a fine "
            "answer; declaring nothing is not."
        )
    if missing:
        details.append(
            f"{len(missing)} changed file(s) are neither declared by section "
            f"{args.scope!r} nor recorded as attributed extras. A section MAY "
            "touch something shared when it cannot proceed otherwise — record "
            "the smallest such change with record_requirement_impact.py "
            "--extra 'PATH=why this section needed it'."
        )
    if missing_deletions:
        details.append(
            f"{len(missing_deletions)} file(s) were DELETED that this section "
            "never declared: " + ", ".join(missing_deletions) + ". Removing "
            "something outside the section's scope needs the same record as "
            "changing it."
        )
    if details:
        payload["detail"] = " ".join(details)
    return _emit(payload, 1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
