"""Record the CI supply-chain acknowledgement required by the F11 gate.

A CI trust-boundary change (`.github/workflows/**`, a hosted dependency-updater
config, composite actions) must name the recorded posture decision it is
consistent with. This CLI computes the run/content binding itself, so nobody
hand-writes the acknowledgement.

The ack is written to ``.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json``
— beside ``reviews.json``. It previously lived in ``iterate_latest`` inside
``shipwright_test_results.json``, which made it impossible to ship: that file is
a DERIVED SNAPSHOT, so committing it trips ``check_no_derived_snapshots_committed``
while omitting it starves ``check_ci_supplychain_ack`` (both ERROR), and
``restore_derived_to_head`` reverted the ack during ordinary finalization
(iterate-2026-07-28-ci-ack-per-run-home).

**Operator-only, now checked, not just documented (trg-33d30377 / PR #718).** A
campaign sub-iterate runner that hits `touches_ci_supplychain` at Step 3.4 must
STOP and hand back — the ack certifies that a human reasoned about a
trust-boundary change, and a runner authoring its own permission slip is exactly
the failure the gate exists to catch (webui #285). That rule used to live only in
prose (`references/campaign-mode.md`); a runner that simply called this CLI
anyway produced an ack that satisfied every check downstream, because run
binding, content binding and field shape all validate a self-written ack
perfectly — authorship was the one property never checked. This CLI now refuses
to run at all while `SHIPWRIGHT_LOOP_UNIT_ID` is set in its own process
environment: that variable is injected around any active autonomous-loop unit
(this campaign's own runner, or an unrelated `shipwright-build --autonomous`
one — see :mod:`tools.ci_supplychain_authorship_guard`) and reaches its
Bash-tool subprocesses via
`capture_session_id.py`'s `CLAUDE_ENV_FILE` write (the SessionStart hook's
`additionalContext` alone is text shown to the model, not an OS environment, so
it cannot be what this guard reads) — see
:func:`refuse_if_campaign_runner_context`. It is never set for a standalone
iterate. **It can still be present for the wrong reason** (nothing unsets it
after a runner returns — copy Step 3b's `export` into your own terminal and
you get refused too; `unset SHIPWRIGHT_LOOP_UNIT_ID` first), and it is a
mitigation, not a cryptographic guarantee: `unset` before invoking this CLI
still defeats it. What it closes is the observed failure — a runner reaching
for this CLI still carrying the context that names it as one. Checked in both
`build_ack` and `write_ack` (doubt review: `write_ack` is independently
reachable, so the check belongs at the actual write, not only its one
documented caller). Every ack also stamps `provenance` (`"worktree"` or
`"commit"`); ``check_ci_supplychain_ack`` rejects one lacking it. A
squash-merge/rebase after recording rewrites the commit SHA and invalidates a
`"commit"`-provenance ack's `provenance_ref` — re-record post-rewrite.

**Two ways to name the content (trg-33d30377's third finding).** The default —
no `--commit` — fingerprints the WORKING TREE, for the pre-F6 window the CI
change is designed to be acknowledged in. Once that change is already
COMMITTED (the operator is acting later, or the working tree has moved on),
the working-tree view sees nothing and the CLI has nothing to fingerprint —
before this flag existed it refused with "no acknowledgement is needed", which
was actively wrong when one plainly was. Pass `--commit <ref>` to fingerprint
that commit's branch diff instead (the same `merge-base..<ref>` view the F11
verifier itself recomputes), so an already-committed CI change stays
acknowledgeable from any later session.

Run it AFTER the final `shipwright_test_results.json` write (F5) and BEFORE the
F6 commit stages it: at that point the CI change lives in the WORKING TREE, which
is what this tool fingerprints by default. The F11 verifier re-fingerprints the
committed content, so any edit to a CI file between recording and committing
invalidates the ack — deliberately, because the recorded sentence would
otherwise describe a change that no longer exists.

Usage::

    uv run shared/scripts/tools/record_ci_supplychain_ack.py \\
      --project-root . --run-id iterate-YYYY-MM-DD-slug \\
      --consistent-with "ADR-042" \\
      --statement "GitHub-owned actions stay on mutable tags; third-party SHA-pinned."

    # Already committed — fingerprint the commit's branch diff instead:
    uv run shared/scripts/tools/record_ci_supplychain_ack.py \\
      --project-root . --run-id iterate-YYYY-MM-DD-slug --commit HEAD \\
      --consistent-with "ADR-042" --statement "..."
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_TOOLS_ROOT = Path(__file__).resolve().parent
if str(_TOOLS_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_TOOLS_ROOT.parent))

from tools.verifiers.ci_supplychain import (  # noqa: E402
    _ci_paths,
    ci_supplychain_fingerprint,
    worktree_reader,
)

# From the module that OWNS them, rather than through a re-export facade: the
# facade claimed to give "one import site for the ack's location" while making the
# same symbols reachable from two public modules (Stage-2 review).
from tools.verifiers.ci_supplychain_ack_store import (  # noqa: E402
    ack_relpath,
    is_safe_run_id,
    wrap_ack,
)
from tools.verifiers.git_blob_read import (  # noqa: E402
    GitReadError,
    committed_bytes_reader,
)
from tools.verifiers.git_helpers import _iterate_changed_paths, _run_git  # noqa: E402
from tools.ci_supplychain_authorship_guard import (  # noqa: E402
    refuse_if_campaign_runner_context,
)


def worktree_ci_paths(project_root: Path) -> list[str]:
    """CI-boundary paths changed in the WORKING TREE (tracked edits + untracked).

    The ack is recorded pre-F6, so the change is not committed yet — asking git for
    a commit range here would find nothing and the tool would refuse to record an
    ack for a change that plainly exists.
    """
    # core.quotePath=false on BOTH: git otherwise quotes a non-ASCII path and
    # escapes its bytes octally, yielding a name that addresses no file. The reader
    # then reports "absent" for it, and since the verifier's side did the same, the
    # fingerprint over that path was content-INDEPENDENT — a measured false-green
    # (Stage-3 doubt review). The writer must produce the same addressable names the
    # verifier does, or the two would simply disagree instead.
    paths: list[str] = []
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false",
                          "diff", "--name-only", "HEAD")
    if rc == 0:
        paths += out.splitlines()
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false",
                          "ls-files", "--others", "--exclude-standard")
    if rc == 0:
        paths += out.splitlines()
    return _ci_paths(paths)


def commit_ci_paths(project_root: Path, commit: str) -> list[str]:
    """CI-boundary paths on the branch diff at ``commit`` — the F11 verifier's own
    ``merge-base..commit`` view (:func:`_iterate_changed_paths`), reused rather than
    re-derived so the two can never independently drift on what "changed" means."""
    changed = _iterate_changed_paths(project_root, commit)
    if changed is None:
        raise SystemExit(
            f"cannot obtain the branch diff for {commit!r} — refusing to compute "
            "a fingerprint over content this tool could not see"
        )
    return _ci_paths(changed)


def _resolve_commit(project_root: Path, ref: str) -> str:
    """Resolve ``ref`` to a full commit SHA. A symbolic ref (``HEAD``, a moving
    branch name) recorded verbatim as ``provenance_ref`` would make the ack's own
    audit trail non-reproducible — it would keep meaning "whatever HEAD was" even
    after HEAD moves on (external review, Branch A)."""
    rc, out, _ = _run_git(project_root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if rc != 0 or not out.strip():
        raise SystemExit(
            f"--commit {ref!r} does not resolve to a commit — refusing to record "
            "an acknowledgement against a ref this tool could not pin down"
        )
    return out.strip()


def build_ack(
    project_root: Path, run_id: str, consistent_with: str, statement: str,
    commit: str | None = None,
) -> dict:
    """Compute the run- and content-bound acknowledgement block.

    Default (``commit`` is ``None``) fingerprints the WORKING TREE — the pre-F6
    window this was designed for. Passing ``commit`` instead fingerprints that
    commit's branch diff, for a CI change that is already committed (trg-33d30377's
    third finding: the working-tree view sees nothing once F6 has run, and refusing
    with "no acknowledgement is needed" was actively wrong in that case).

    Defense in depth: also refuses inside a campaign runner context here, not
    only in ``main()`` — mirrors ``write_ack``'s own ``is_safe_run_id`` guard, so
    a future caller that reaches this function without going through the CLI
    inherits the refusal rather than a silent gap (external review, Branch A).
    """
    refuse_if_campaign_runner_context()
    if commit:
        commit = _resolve_commit(project_root, commit)
        where = f"commit {commit!r}"
        ci_paths = commit_ci_paths(project_root, commit)
        reader = committed_bytes_reader(project_root, commit)
        provenance, provenance_ref = "commit", commit
    else:
        where = "the working tree"
        ci_paths = worktree_ci_paths(project_root)
        reader = worktree_reader(project_root)
        provenance, provenance_ref = "worktree", None
    if not ci_paths:
        suggestion = (
            "" if commit else
            " — if this CI change is already committed, pass --commit <ref> to "
            "acknowledge the committed content instead"
        )
        raise SystemExit(
            f"{where} touches no CI supply-chain file — no acknowledgement is "
            f"needed (and recording one would only plant a stale ack for later){suggestion}"
        )
    try:
        fingerprint = ci_supplychain_fingerprint(ci_paths, reader)
    except GitReadError as exc:
        # Mirrors the verifier's own posture: a read failure must never be hashed
        # as "<absent>", the value a genuinely deleted path gets.
        raise SystemExit(
            f"could not read committed content for {where} ({exc}) — refusing to "
            "compute a fingerprint over content this tool could not see"
        ) from exc
    return {
        "run_id": run_id,
        "paths_fingerprint": fingerprint,
        "consistent_with": consistent_with.strip(),
        "statement": statement.strip(),
        "ci_paths": ci_paths,
        "provenance": provenance,
        "provenance_ref": provenance_ref,
    }


def write_ack(project_root: Path, run_id: str, ack: dict) -> Path:
    """Write the ack to its own per-run file, beside ``reviews.json``.

    It used to be merged into ``iterate_latest`` in ``shipwright_test_results.json``.
    That file is a DERIVED SNAPSHOT, which made the ack unshippable: committing it
    trips ``check_no_derived_snapshots_committed`` and omitting it starves
    ``check_ci_supplychain_ack`` (both ERROR), while ``restore_derived_to_head``
    reverted it outright during finalization. The per-run path is tracked, not
    derived, and collides with no other run.

    Written atomically: an interrupted write would otherwise leave a half-file
    that fails the gate for a reason unrelated to the CI change itself.

    Guarded here too (doubt review, trg-33d30377): this is the function that
    actually touches disk and is importable on its own, bypassing
    ``build_ack``'s guard entirely if called directly with a hand-built dict.
    """
    refuse_if_campaign_runner_context()
    if not is_safe_run_id(run_id):
        raise SystemExit(
            f"run id {run_id!r} is not a single safe path component — it becomes a "
            "directory name under .shipwright/planning/iterate/"
        )
    path = project_root / ack_relpath(run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(wrap_ack(run_id, ack), indent=2, ensure_ascii=False) + "\n"
    # with_name, not with_suffix: `with_suffix` REPLACES the final suffix, so it
    # only happens to be correct while the filename has exactly one dot.
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        # A leftover .tmp from a failed write would otherwise be swept into the PR
        # by F6's DIRECTORY-level add on the next successful run (Stage-2 review).
        # No-op after a successful replace.
        tmp.unlink(missing_ok=True)
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Record the CI supply-chain acknowledgement")
    ap.add_argument("--project-root", default=".", help="iterate worktree root")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--consistent-with", required=True,
                    help="the recorded decision this change agrees with (ADR-NNN, "
                         "an iterate-YYYY-MM-DD-slug run id, or #NNN)")
    ap.add_argument("--statement", required=True,
                    help="what this change does to the CI trust boundary")
    ap.add_argument("--commit", default=None,
                    help="fingerprint this commit's branch diff instead of the "
                         "working tree — for a CI change that is already committed")
    args = ap.parse_args(argv)

    # Cheapest, most certain rejection FIRST — before any git call or path
    # computation. No override: this refusal is unconditional.
    refuse_if_campaign_runner_context()

    root = Path(args.project_root).resolve()
    # Validating it only inside write_ack meant an unsafe run id on a tree with no
    # CI change was reported as "touches no CI supply-chain file" — the wrong
    # diagnosis (Stage-2 review). The guard in write_ack stays as the API-level
    # one for non-CLI callers.
    if not is_safe_run_id(args.run_id):
        raise SystemExit(
            f"run id {args.run_id!r} is not a single safe path component — it "
            "becomes a directory name under .shipwright/planning/iterate/"
        )
    ack = build_ack(root, args.run_id, args.consistent_with, args.statement, args.commit)
    path = write_ack(root, args.run_id, ack)
    print(json.dumps({"written": str(path), "ci_supplychain_ack": ack}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
