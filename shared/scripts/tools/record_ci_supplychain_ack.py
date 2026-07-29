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

Run it AFTER the final `shipwright_test_results.json` write (F5) and BEFORE the
F6 commit stages it: at that point the CI change lives in the WORKING TREE, which
is what this tool fingerprints. The F11 verifier re-fingerprints the committed
content, so any edit to a CI file between recording and committing invalidates the
ack — deliberately, because the recorded sentence would otherwise describe a
change that no longer exists.

Usage::

    uv run shared/scripts/tools/record_ci_supplychain_ack.py \\
      --project-root . --run-id iterate-YYYY-MM-DD-slug \\
      --consistent-with "ADR-042" \\
      --statement "GitHub-owned actions stay on mutable tags; third-party SHA-pinned."
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
from tools.verifiers.git_helpers import _run_git  # noqa: E402


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


def build_ack(project_root: Path, run_id: str, consistent_with: str, statement: str) -> dict:
    """Compute the run- and content-bound acknowledgement block."""
    ci_paths = worktree_ci_paths(project_root)
    if not ci_paths:
        raise SystemExit(
            "the working tree touches no CI supply-chain file — no acknowledgement "
            "is needed (and recording one would only plant a stale ack for later)"
        )
    return {
        "run_id": run_id,
        "paths_fingerprint": ci_supplychain_fingerprint(ci_paths, worktree_reader(project_root)),
        "consistent_with": consistent_with.strip(),
        "statement": statement.strip(),
        "ci_paths": ci_paths,
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
    """
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
    args = ap.parse_args(argv)

    root = Path(args.project_root).resolve()
    # Cheapest, most certain rejection FIRST. Validating it only inside write_ack
    # meant an unsafe run id on a tree with no CI change was reported as "touches
    # no CI supply-chain file" — the wrong diagnosis (Stage-2 review). The guard in
    # write_ack stays as the API-level one for non-CLI callers.
    if not is_safe_run_id(args.run_id):
        raise SystemExit(
            f"run id {args.run_id!r} is not a single safe path component — it "
            "becomes a directory name under .shipwright/planning/iterate/"
        )
    ack = build_ack(root, args.run_id, args.consistent_with, args.statement)
    path = write_ack(root, args.run_id, ack)
    print(json.dumps({"written": str(path), "ci_supplychain_ack": ack}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
