#!/usr/bin/env python3
"""Deliver the recomputed compliance evidence documents. Three ways, one producer.

* ``--stage``   the **release** path. Regenerate, verify, ``git add`` exactly the
  seven, and print the pathspec the release commit must use.
* ``--pr``      the **on-demand** path. Same producer on a branch off a freshly
  fetched default branch, take-the-set so nothing else can ride along, then an
  ordinary pull request under the operator's own ``gh`` login.
* ``--restore`` reset the seven to ``HEAD``. The changelog skill's
  phase-completion call regenerates them a second time — unstamped, at a
  different commit — and without this the release ends with a permanently dirty
  worktree (external review, openai/high).

There is **no robot with write access to the default branch** anywhere in this
file: no key, no secret, no ruleset bypass, no workflow, and nothing that runs in
CI. Both delivery paths go through a pull request a human opens and reviews. That
is the whole point of the path this implements — decision paper:
``.shipwright/planning/iterate/2026-07-30-derived-snapshots-decision.md``.

Recompute-and-verify lives in :mod:`tools.compliance_refresh_produce`; which paths
and why in :mod:`lib.compliance_refresh`; what each document then claims about
itself in :mod:`tools.compliance_provenance`; the git primitives and the whole
on-demand PR protocol in :mod:`tools.compliance_delivery`.

Trusted use only. Every ``git`` / ``gh`` call is an argv list, never a shell
string, and every value that reaches a ref name or a provenance banner is
validated first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# UNCONDITIONAL — see the note in `tools/compliance_refresh_produce.py` (ADR-045).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.compliance_refresh import REFRESH_SET, release_commit_note  # noqa: E402
from source_state import parse_banner_line, safe_commit, safe_run_id  # noqa: E402
from tools.compliance_delivery import deliver_pr, preflight_pr  # noqa: E402
from tools.compliance_git import (  # noqa: E402
    restore_to_head,
    staged_difference,
    write_back,
)
from tools.compliance_adopt_stamp import deliver_stamp_adopted  # noqa: E402
from tools.compliance_refresh_produce import git, produce  # noqa: E402

__all__ = ["deliver_stage", "main", "verify_commit"]


def verify_commit(root: Path, sha: str) -> dict:
    """Assert the COMMIT carries the stamp. The only check that reads the artifact.

    ``git commit -- <pathspec>`` commits the contents of the matching files
    **without recording the changes already staged** — it reads the WORKING TREE.
    Every other check in this change reads the index, so a writer touching
    ``.shipwright/compliance/*.md`` between Step 5.5 and Step 6 — a Stop hook, a
    background ``update_compliance``, a second session — substitutes unstamped
    bytes into the release commit while the tool's JSON and every test still say
    ``stamped: [...]``.

    That is the Stage-1 HIGH-1 defect one step downstream of where it was fixed,
    and it is invisible for exactly the reason HIGH-1 was: the run's own evidence
    is a return value rather than the artifact (Stage-3 doubt D2). So this reads
    the artifact.
    """
    missing: list[str] = []
    for rel in sorted(REFRESH_SET):
        if not rel.endswith(".md"):
            continue  # the two .json members carry no banner by design
        blob = git(root, "show", f"{sha}:{rel}")
        if blob.returncode != 0:
            continue  # absent from this commit — the pathspec is presence-filtered
        state = parse_banner_line(blob.stdout or "")
        if state is None or not state.base:
            missing.append(rel)
    return {
        "status": "verified" if not missing else "unstamped_in_commit",
        "commit": sha, "unstamped": missing,
    }


def deliver_stage(
    root: Path, result: dict, payload: dict[str, bytes], release: str | None,
) -> dict:
    """Write the stamped bytes back, stage exactly the seven, hand back the pathspec.

    Staging alone does NOT bound the release commit: ``git add`` is additive, so
    anything an earlier step or the operator already staged would ride an
    unqualified ``git commit`` (external review, openai/high). The boundary is
    therefore the COMMIT, and the printed pathspec is what makes it exact
    whatever else the index holds.
    """
    write_back(root, payload)
    staged = staged_difference(root, sorted(REFRESH_SET))
    if staged is None:
        result["status"] = "stage_failed"
        result["detail"] = ("git could not stage the evidence paths — do NOT tag; "
                            "the release commit would carry stale documents")
        return result
    result["staged"] = staged
    # The EVIDENCE paths only — this tool owns the seven, not the release's own
    # artifacts (CHANGELOG.md, the folded decision log, the ADR folder), which the
    # changelog skill adds itself. Naming them here would make the tool the owner
    # of a list it cannot maintain.
    #
    # PRESENCE-FILTERED: `git commit -- <pathspec>` aborts outright on a path that
    # matches no file, and a project cutting its first release has never run a CI
    # scan, so `ci-security.json` does not exist — the printed command would fail
    # with `fatal: pathspec ... did not match any files` and commit nothing
    # (Stage-3 doubt D7). Every test fixture commits all seven, so this was
    # invisible.
    result["evidence_pathspec"] = [
        rel for rel in sorted(REFRESH_SET) if (root / rel).is_file()]
    if release:
        result["note"] = release_commit_note(release)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Recompute the compliance evidence documents and deliver them")
    parser.add_argument("--project-root", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--stage", action="store_true",
                      help="regenerate and stage the seven for the release commit")
    mode.add_argument("--pr", action="store_true",
                      help="regenerate on a fresh branch and open a documents-only PR")
    mode.add_argument("--restore", action="store_true",
                      help="reset the seven to HEAD after the release phase-completion regen")
    mode.add_argument("--verify-commit", metavar="SHA", default=None,
                      help="assert the named commit really carries the stamp — "
                           "`git commit -- <paths>` reads the WORKTREE, so the index "
                           "checks everything else does prove nothing about it")
    mode.add_argument("--stamp-adopted", action="store_true",
                      help="stamp the seeded evidence at onboarding with the commit "
                           "the repository was read at (--base). Does NOT recompute "
                           "and never resolves HEAD — only the caller knows that "
                           "commit")
    parser.add_argument("--base", default=None,
                        help="the commit onboarding read, for --stamp-adopted. "
                             "PASSED IN, never observed: at Step H this process's "
                             "HEAD equals it only if nothing has committed since")
    parser.add_argument("--release", default=None,
                        help="the release this ships with, e.g. v0.5.2. PASSED IN — the "
                             "tag does not exist yet at the moment this runs")
    parser.add_argument("--run-id", default="compliance-docs-refresh")
    parser.add_argument("--allow-shrink", action="store_true",
                        help="waive the ratio content floor for a legitimate large removal")
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()

    if args.verify_commit:
        sha = safe_commit(args.verify_commit)
        if not sha:
            parser.error(f"--verify-commit {args.verify_commit!r} is not a commit")
        report = verify_commit(root, sha)
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "verified" else 1

    if args.restore:
        moved, unresolved = restore_to_head(root)
        # At Step 8 of a release this is the difference between "the committed
        # stamped copies won" and "the worktree still holds the second, unstamped
        # regeneration". Reporting both identically is how the operator tags on a
        # tree that disagrees with what shipped (Stage-2 code review, low).
        print(json.dumps({
            "status": "restored" if not unresolved else "restore_incomplete",
            "restored": moved, "unresolved": unresolved,
        }, indent=2))
        return 0 if not unresolved else 1

    # Onboarding's delivery. Returns HERE, before the `rev-parse HEAD` below:
    # this mode must never resolve HEAD, and the surest way to guarantee that is
    # for the code that does it to be unreachable from this path.
    if args.stamp_adopted:
        report = deliver_stamp_adopted(root, args.base)
        print(json.dumps(report, indent=2))
        # `no_base` is a success: a repository with no commits is a legitimate
        # thing to onboard, and an unstamped banner is the honest outcome.
        # `partial` (present but unstampable) and `no_documents` (Step F produced
        # nothing) are errors, and must be non-zero ones — a wrapper that checks
        # the exit code would otherwise commit a half-stamped or empty set.
        return 0 if report["status"] in ("ok", "no_base") else 1

    # A documents-only branch off the default branch did not ship with any
    # release. Stamping the latest tag would claim it did; choosing silently would
    # give one producer two meanings. Refuse, and let the operator say which.
    if args.pr and args.release:
        parser.error("--release belongs to the release delivery; a documents-only "
                     "PR ships with no release and must not claim one")
    release = safe_run_id(args.release) if args.release else None
    if args.release and release is None:
        parser.error(f"--release {args.release!r} is not a single usable token")

    result: dict = {}
    if args.pr:
        refusal = preflight_pr(root, result)
        if refusal:
            print(json.dumps({"status": "refused", "detail": refusal}, indent=2))
            return 2
    base_sha = safe_commit((git(root, "rev-parse", "HEAD").stdout or "").strip())
    if not base_sha:
        print(json.dumps({"status": "refused", "detail": "HEAD did not resolve"},
                         indent=2))
        return 2

    # Everything that can leave regenerated-AND-STAGED content behind lives inside
    # this boundary. `regenerate_tracked_snapshots` stages what it writes, so an
    # uncaught raise — an ImportError from the compliance plugin, a producer
    # exception — would hand the operator a dirty index and a traceback, and the
    # NEXT run would then refuse preflight over changes they never made (Stage-2
    # code review, medium).
    try:
        produced, payload = produce(
            root, args.run_id, base_sha, release, allow_shrink=args.allow_shrink)
        produced.update(result)
        produced["run_id"] = args.run_id
        if produced["status"] != "ok":
            # `produce` has already rewound the seven to the state it FOUND them
            # in, so nothing untrusted is left for the next `git add` to pick up.
            # Deliberately not `restore_to_head`: that resets to HEAD and would
            # discard an operator edit while cleaning up after a refusal that was
            # not theirs (external code review, openai/medium).
            print(json.dumps(produced, indent=2))
            return 1

        delivered = (deliver_pr(root, produced, payload) if args.pr
                     else deliver_stage(root, produced, payload, release))
    except Exception as exc:  # noqa: BLE001 — a crash must still leave a clean tree
        # HEAD-resetting, and deliberately, even though `produce` argues the
        # opposite for its own refusals (Stage-3 doubt D5). The difference is what
        # is known: a refusal happens with `produce`'s found-state snapshot in
        # hand, so it can rewind precisely; a crash happens with that frame gone
        # and the tree in an unknown partial state, where "leave no untrusted
        # regenerated content staged" is the only guarantee still worth making.
        # The cost is stated rather than hidden: an uncommitted operator edit to
        # one of the seven does not survive a crash here.
        moved, unresolved = restore_to_head(root)
        print(json.dumps({
            "status": "crashed", "error": f"{type(exc).__name__}: {exc}"[:400],
            "restored": moved, "unresolved": unresolved,
        }, indent=2))
        return 1
    print(json.dumps(delivered, indent=2))
    return 0 if delivered["status"] in ("ok", "noop", "pr_opened") else 1


if __name__ == "__main__":
    raise SystemExit(main())
