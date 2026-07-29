"""Where the CI supply-chain acknowledgement lives, and how it is loaded.

Split from ``ci_supplychain.py`` (which keeps flag detection, fingerprinting and
field validation) so neither file crosses the 300-line rule — the same reason
``derived_snapshot_gate.py`` is its own module.

**The ack used to live in ``shipwright_test_results.json``**, and that made two
ERROR-severity F11 checks contradict each other for any iterate touching
``.github/workflows/**`` (iterate-2026-07-28-ci-ack-per-run-home):

- ``check_ci_supplychain_ack`` read the ack from the COMMITTED results file. Its
  disk fallback only fired when ``git show`` *failed* — i.e. when the file was
  untracked at that commit. It is tracked on ``main``, so the committed, ack-less
  copy always won.
- ``check_no_derived_snapshots_committed`` errors when the commit touches that
  same file, because it is a :data:`DERIVED_SNAPSHOTS` path.

Commit it and the second fails; omit it and the first does. Worse,
``restore_derived_to_head`` reverted a correctly-recorded ack during ordinary
finalization hygiene. Observed on PR 497 and resolved there by committing the
file — right under duress, wrong to institutionalise. And the parked
derived-snapshots refresh moves the file off branches entirely, which would make
the ack *unreachable* rather than merely conflicted.

The ack now lives per-run, beside ``reviews.json``: tracked, not derived, and
unable to collide between parallel iterates because no two runs share a path.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.review_record_schema import is_safe_run_id  # noqa: E402

from .git_blob_read import read_committed_text  # noqa: E402

__all__ = [
    "ACK_FILENAME", "SCHEMA_VERSION", "ack_relpath", "is_safe_run_id",
    "load_ack", "source_caveat", "wrap_ack",
]

#: Beside ``reviews.json`` in the run's own planning directory.
ACK_FILENAME = "ci_supplychain_ack.json"
_RESULTS = "shipwright_test_results.json"
#: The envelope shape this verifier knows how to read.
SCHEMA_VERSION = 1


def ack_relpath(run_id: str) -> str:
    """Repo-relative POSIX path of the per-run ack.

    ``run_id`` becomes a DIRECTORY NAME, so an unsafe one must be rejected with
    :func:`is_safe_run_id` — ``..`` would traverse out of the planning tree. (An
    ABSOLUTE run_id is inert here, unlike in ``review_record_schema.record_dir``
    from which this guard is borrowed, because the f-string prefix keeps the
    result relative; the docstring used to claim that hazard too — Stage-2 review.)
    :func:`load_ack` enforces the guard itself rather than trusting callers.
    """
    return f".shipwright/planning/iterate/{run_id}/{ACK_FILENAME}"


def wrap_ack(run_id: str, ack: dict) -> dict:
    """The on-disk envelope, shaped like its neighbour ``reviews.json``."""
    return {"schema_version": SCHEMA_VERSION, "run_id": run_id,
            "ci_supplychain_ack": ack}


def source_caveat(source: str) -> str:
    """Render the ``load_ack`` source tag for the check's detail line.

    Lives beside the producer of that vocabulary on purpose: while the tags were
    minted here and rendered in ``ci_supplychain.py``, the two drifted — the
    ``legacy-worktree`` case was minted without a matching caveat and silently
    dropped the non-shipping warning (external code review).
    """
    not_shipping = ("read from the working tree, not the commit; "
                    "stage it or it will not ship in the PR")
    return {
        "worktree": f" — NOTE: {not_shipping}",
        "legacy": " — via the legacy iterate_latest key",
        "legacy-worktree": f" — via the legacy iterate_latest key; NOTE: {not_shipping}",
    }.get(source, "")


def _parse_per_run(body: str, rel: str) -> tuple[dict | None, str | None]:
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, f"{rel} is unreadable/corrupt ({exc})"
    if not isinstance(data, dict):
        return None, f"{rel} is not a JSON object"
    # Make the version load-bearing rather than decorative: an unrecognised
    # envelope read with v1 semantics is the one place a future format change
    # would be MISread instead of failing closed (Stage-2 review). Absent is
    # accepted so a hand-written ack is not rejected for want of ceremony.
    version = data.get("schema_version")
    if version not in (SCHEMA_VERSION, None):
        return None, (f"{rel} is schema_version {version!r}, which this verifier "
                      f"cannot read (expected {SCHEMA_VERSION})")
    ack = data.get("ci_supplychain_ack")
    if not isinstance(ack, dict):
        return None, f"{rel} carries no `ci_supplychain_ack` object"
    return ack, None


def _read_legacy(
    project_root: Path, commit: str
) -> tuple[dict | None, str | None, bool]:
    """The pre-relocation home: ``iterate_latest.ci_supplychain_ack`` inside
    ``shipwright_test_results.json`` — a KEY in that file, not a file of its own.

    Kept so in-flight branches that already recorded an ack the old way do not
    red-line at F11 for a reason they cannot act on without a rebase. It is a
    different LOCATION, not a weaker rule: the caller applies identical run-id,
    fingerprint and field validation to whatever this returns.

    Reads through :func:`~.git_blob_read.read_committed_text` rather than its own
    ``git show``: that spelling carries the ``MAX_PATH`` trap documented there, and
    keeping a second copy of the bug in the fallback leg would mean the legacy path
    failed on exactly the deep checkouts the new path was fixed for. It also gains
    the same absent-vs-broken discrimination.

    Third return value is ``from_commit``. The legacy leg has the same durability
    question as the per-run one — a results file absent from the commit but present
    on disk yields an ack that will not ship — and reporting it merely as "legacy"
    dropped the non-shipping warning for exactly that case (external code review).
    """
    raw, err = read_committed_text(project_root, commit, _RESULTS)
    if err:
        return None, err, False
    from_commit = raw is not None
    if raw is None:
        path = project_root / _RESULTS
        if not path.exists():
            return None, None, False
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"{_RESULTS} is unreadable/corrupt ({exc})", False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"{_RESULTS} is unreadable/corrupt ({exc})", from_commit
    if not isinstance(data, dict):
        return None, f"{_RESULTS} is not a JSON object", from_commit
    latest = data.get("iterate_latest")
    if not isinstance(latest, dict):
        return None, None, from_commit
    ack = latest.get("ci_supplychain_ack")
    return (ack if isinstance(ack, dict) else None), None, from_commit


def load_ack(
    project_root: Path, run_id: str, commit: str = ""
) -> tuple[dict | None, str | None, str]:
    """Resolve the authoritative ack. Returns ``(ack, error, source)``.

    ``source`` is one of ``"commit"``, ``"worktree"``, ``"legacy"``,
    ``"legacy-worktree"`` or ``""``, so the caller can say WHERE the ack came from.
    Either ``*-worktree`` value means the record is not in the commit and will not
    ship in the PR — the gate still passes, but silently passing on an unshippable
    record is exactly the ambiguity this whole change exists to remove, so it is
    reported rather than hidden. The legacy leg carries the distinction too:
    collapsing it to a bare ``"legacy"`` dropped the warning for a results file that
    was present on disk but absent from the commit (external code review).

    Sources are tried in order — committed per-run file, working-tree per-run
    file, then the legacy results-file key — but **the first source that is
    PRESENT is authoritative and terminal**. Only genuine absence advances.

    That distinction is the whole safety property. If a present-but-invalid
    per-run ack quietly deferred to a valid legacy one, the new home would be
    bypassable: park a good old-style ack, then write anything at all to the new
    path. So "unreadable", "malformed" and "semantically wrong" all fail here or
    in the caller's validation — they never hand off to the next source.
    """
    # Guarded HERE, not only in the callers: this function builds a filesystem path
    # from `run_id`, and both public entry points (`ack_relpath`, `load_ack`) are
    # exported. Leaving the guard to a caller in a different module means a future
    # third caller inherits an arbitrary-file read (Stage-2 review, defence in
    # depth — both shipped callers do guard, so there is no live path today).
    if not is_safe_run_id(run_id):
        return None, f"run id {str(run_id)[:60]!r} is not a safe path component", ""
    rel = ack_relpath(run_id)
    body, err = read_committed_text(project_root, commit, rel)
    if err:
        return None, err, ""
    source = "commit"
    if body is None:
        # Genuinely absent from the commit: a brand-new ack file that has not been
        # staged yet is the normal pre-F6 state, so the working copy may answer.
        worktree_copy = project_root / rel
        # exists() but not is_file() — a directory, a broken symlink, an EACCES stat
        # — is PRESENT, so advancing to the legacy leg would break the stated
        # invariant even though it grants no privilege (plain absence already
        # licenses legacy). Stage-3 doubt review: make the code match the sentence.
        if worktree_copy.exists() and not worktree_copy.is_file():
            return None, f"{rel} exists but is not a regular file", ""
        if worktree_copy.is_file():
            source = "worktree"
            try:
                body = worktree_copy.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as exc:
                return None, f"{rel} is unreadable/corrupt ({exc})", ""
    if body is not None:
        ack, parse_err = _parse_per_run(body, rel)
        return ack, parse_err, ("" if parse_err else source)
    ack, legacy_err, from_commit = _read_legacy(project_root, commit)
    if not ack or legacy_err:
        return ack, legacy_err, ""
    return ack, None, ("legacy" if from_commit else "legacy-worktree")
