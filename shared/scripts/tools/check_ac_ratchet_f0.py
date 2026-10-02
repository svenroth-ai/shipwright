#!/usr/bin/env python3
"""Run ci.yml's `AC coverage ratchet (gate)` at F0, against F0's OWN test run.

The ratchet reads which ACs are bound from the traceability manifest, and the manifest's
per-test ``executed`` claims come from a real JUnit run. CI regenerates the manifest in
place from its run's JUnit before gating. Locally the committed manifest is the only one
on disk, so gating against it would grade the working tree on execution claims nobody
re-verified - the self-vouching `scripts/verify_local.py` lists this gate as un-mirrorable
for. F0 retains each unit's real JUnit (`suite_retention.py`), so that reason is gone:

  1. Refuse unless the retained run for ``--run-id`` is complete and green
     (`stage_f0_evidence.validated_junit_reports` - the same refusals staging applies).
  2. Copy the working tree (tracked + untracked, non-ignored files) to a SCRATCH root
     under ``<project>/.scratch/`` (short and gitignored). The manifest and evidence are
     never written in ``--project-root``: the manifest is a TRACKED file, and an in-place
     regeneration would dirty the tree F6 is about to commit.
  3. Stage the retained JUnit into the scratch root (so the regenerated manifest has the
     same shape CI's has), regenerate the manifest there from the WORKING TREE's
     ``@covers`` tags with this tree's compliance plugin, and run
     `check_ac_coverage_ratchet.py` on the scratch.

What makes the verdict honest is step 3's regeneration: a committed manifest can lag the
working tree's tags. The ratchet counts an AC as bound by link existence, so the JUnit
does not decide the verdict - it only shapes the regenerated manifest like CI's.

No-op (exit 0, with a notice) unless the project actually has this gate to mirror: both
``plugins/shipwright-compliance`` and ``shipwright_ac_coverage_baseline.json``.

Exit codes follow the ratchet's own dialect: ``0`` clean, ``1`` a new unbound AC outside
the baseline, ``2`` infrastructure (no/red/incomplete retained run, copy or regeneration
failed). **Not covered here, by design:** `Repair-PR safety (gate)` materialises its
checker from the PR's base revision, which a branch cannot do to itself - it stays CI-only.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

_SHARED_ROOT = Path(__file__).resolve().parents[2]
if str(_SHARED_ROOT) not in sys.path:
    sys.path.insert(0, str(_SHARED_ROOT))
from scripts.lib import evidence_drop  # noqa: E402
from scripts.tools import ci_manifest_drift_check as _regen  # noqa: E402
from scripts.tools import stage_f0_evidence as _f0  # noqa: E402

EXIT_OK = 0
EXIT_BLOCKED = 1
EXIT_INFRA = 2

_RATCHET = Path(__file__).resolve().parent / "check_ac_coverage_ratchet.py"
_COMPLIANCE_PLUGIN = Path("plugins") / "shipwright-compliance"
_BASELINE = "shipwright_ac_coverage_baseline.json"
_TIMEOUT_SECONDS = 900


class RatchetF0Error(Exception):
    """Something before the ratchet itself could run - always exit 2."""


def _git(root: Path, *args: str) -> bytes:
    proc = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
        ["git", "-C", str(root), *args], capture_output=True, check=False, shell=False,
    )
    if proc.returncode != 0:
        raise RatchetF0Error(
            f"git {' '.join(args)} failed in {root}: "
            f"{proc.stderr.decode('utf-8', 'replace').strip()}"
        )
    return proc.stdout


def _has_symlinked_ancestor(root: Path, path: Path) -> bool:
    """True when a directory BETWEEN ``root`` and ``path`` is a symlink. Reading or writing
    through one would leave the project (source) or the scratch root (destination)."""
    parent = path.parent
    while parent != root and root in parent.parents:
        if parent.is_symlink():
            return True
        parent = parent.parent
    return False


def snapshot_tree(root: Path, dest: Path) -> int:
    """Copy every tracked-or-untracked, non-ignored file of ``root`` into ``dest``.

    The same file set `git add -A` would stage, which is the tree F6 commits and CI
    checks out. Symlinks are skipped (regular files only). A tracked path deleted from the working tree is skipped, not an error.
    Returns the number of files copied.
    """
    listing = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    copied = 0
    for raw in sorted({p for p in listing.split(b"\0") if p}):
        rel = raw.decode("utf-8", "surrogateescape")
        src = root / rel
        target = dest / rel
        if _has_symlinked_ancestor(root, src):
            continue  # git cannot track a path beneath a link; a stale artifact, never copy
        if src.is_symlink():
            # The scratch tree holds REGULAR FILES ONLY. A recreated link would let the
            # later staging / regeneration writes follow it out of scratch, and a followed
            # one would copy content from outside the project; the ratchet reads only
            # @covers tags and spec text, which never live behind a link.
            continue
        if not src.is_file():
            continue  # deleted in the working tree, or a gitlink / submodule directory
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
        copied += 1
    return copied


def run(project_root: Path, run_id: str, scratch_parent: Path | None = None) -> int:
    try:
        return _run(project_root, run_id, scratch_parent)
    except Exception as exc:  # noqa: BLE001 - last-resort boundary: an unanticipated fault
        # (timeout, odd path) must be exit 2, never Python's bare 1, which aliases with
        # EXIT_BLOCKED and tells the operator to go bind an AC that is not the problem.
        print(f"ERROR: unexpected failure: {exc!r}", file=sys.stderr)
        return EXIT_INFRA


def _run(project_root: Path, run_id: str, scratch_parent: Path | None) -> int:
    if not ((project_root / _COMPLIANCE_PLUGIN).is_dir() and (project_root / _BASELINE).is_file()):
        print(f"SKIP: no {_COMPLIANCE_PLUGIN.as_posix()} + {_BASELINE} here - this project "
              "does not run the AC coverage ratchet, nothing to mirror.")
        return EXIT_OK
    if scratch_parent is None:
        scratch_parent = project_root / ".scratch"  # short + gitignored (MAX_PATH headroom)
    scratch_parent.mkdir(parents=True, exist_ok=True)
    try:
        run_dir, junit_reports = _f0.validated_junit_reports(project_root, run_id)
    except _f0.StageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_INFRA
    if _f0.published_resumed(run_dir):
        print("NOTE: the retained F0 run is a RESUME (reused/red-only results); the JUnit "
              "is resumed-local evidence, CI re-runs everything.")

    with tempfile.TemporaryDirectory(
        prefix="acr-", dir=scratch_parent, ignore_cleanup_errors=True,
    ) as tmp:
        scratch = Path(tmp)
        try:
            snapshot_tree(project_root, scratch)
            evidence_drop.stage_reports(
                scratch, run_id=run_id, head_commit="", junit_reports=junit_reports,
            )
            _regen.regenerate_manifest(
                scratch, plugin_root=project_root / _COMPLIANCE_PLUGIN,
            )
        except (RatchetF0Error, _regen.DriftCheckError, OSError) as exc:
            print(f"ERROR: could not build the scratch manifest: {exc}", file=sys.stderr)
            return EXIT_INFRA
        proc = subprocess.run(  # nosec B603,B607 - fixed argv, shell=False
            [sys.executable, str(_RATCHET), "--project-root", str(scratch)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            check=False, shell=False, timeout=_TIMEOUT_SECONDS,
        )
    print(proc.stdout, end="")
    if proc.stderr.strip():
        print(proc.stderr, end="", file=sys.stderr)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project-root", default=".", type=Path)
    ap.add_argument("--run-id", required=True, help="the run id F0's `run_test_suite.py` was given")
    args = ap.parse_args(argv)
    return run(args.project_root.resolve(), args.run_id)


if __name__ == "__main__":
    raise SystemExit(main())
