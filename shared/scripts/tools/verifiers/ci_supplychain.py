"""``touches_ci_supplychain`` acknowledgement gate.

The CI trust boundary — `.github/workflows/**`, the dependency-updater config and
composite actions — decides WHICH third-party code runs with repository
credentials. Before iterate-2026-07-18-ci-supplychain-risk-flag it fired no risk
flag at all: webui PR #285 reversed an accepted-risk posture while recording
``risk_flags: []`` through a full medium iterate (external plan review, code
review, confidence calibration), and its revert reproduced the same blind spot.

Mandatory *review* was therefore not the fix — #285 already had more review than
that would impose. This gate instead forces an explicit written acknowledgement:
the author must name the recorded posture decision the change is consistent with.
That is the sentence nobody could have written for #285 without noticing the
contradiction.

The ack is bound to the run id AND a fingerprint of this diff's CI paths *and
their content*. Without the run binding, a leftover ack would satisfy the gate for
any later CI change; without the content binding, an author could acknowledge
"adds a ruff step" and then slip `pull_request_target:` into the same file before
committing. Both were false-greens by construction.

Where the ack LIVES and how it is loaded is :mod:`ci_supplychain_ack_store`;
reading committed content safely is :mod:`git_blob_read`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from .ci_supplychain_ack_store import (  # noqa: E402
    ack_relpath,
    is_safe_run_id,
    load_ack,
    source_caveat,
)
from .common import CheckResult, Severity  # noqa: E402
from .git_blob_read import (  # noqa: E402
    GitReadError,
    committed_bytes_reader,
    content_fingerprint,
    worktree_bytes_reader,
)
from .git_helpers import _iterate_changed_paths, _run_git, git_context  # noqa: E402

# Self-contained copy of ``risk_detectors.CI_SUPPLYCHAIN_FILE_PATTERNS`` so this
# load-bearing verifier never cross-plugin-imports the iterate-plugin lib
# (ADR-044). The drift test ``test_ci_supplychain_patterns_sync`` pins this ==
# the SSoT, forward + reverse.
_CI_SUPPLYCHAIN_PATTERNS = (
    r"^\.github/workflows/.+\.ya?ml$",
    r"^\.github/dependabot\.ya?ml$",
    r"^\.github/actions/.+$",
    # Any hosted dependency-updater config, not just Dependabot: reintroducing the
    # posture under a different filename must not escape the gate.
    r"^\.github/renovate\.json5?$",
    r"^renovate\.json5?$",
    r"^\.renovaterc(\.json)?$",
    # Shipped CI templates — the adopters' trust boundary (trg-6e8121e7).
    r"^shared/templates/github-actions/.+$",
)


def _normalize(path: str) -> str:
    """Repo-relative POSIX path. `git` quotes non-ASCII paths by default
    (core.quotePath), and a leading quote would defeat the `^` anchor."""
    norm = path.replace("\\", "/").strip()
    if len(norm) >= 2 and norm.startswith('"') and norm.endswith('"'):
        norm = norm[1:-1]
    return norm

# `consistent_with` must NAME a recorded decision, not merely be non-empty —
# "N/A" / "TODO" / "we talked about it" are exactly the filler the gate exists to
# refuse. Simple literal alternation with bounded classes: linear, no nested
# quantifiers (ReDoS-safe).
_DECISION_REF_RE = re.compile(
    r"(ADR-\d+|iterate-\d{4}-\d{2}-\d{2}-[a-z0-9-]+|#\d+)", re.IGNORECASE
)
_MIN_STATEMENT_CHARS = 20
_MIN_REF_CHARS = 3
_MIN_STATEMENT_WORDS = 5


def _is_ci_supplychain(changed_files: list[str] | None) -> bool:
    for path in changed_files or []:
        norm = _normalize(path)
        for pat in _CI_SUPPLYCHAIN_PATTERNS:
            if re.search(pat, norm):
                return True
    return False


def _ci_paths(changed_files: list[str] | None) -> list[str]:
    """The CI-boundary subset of a diff, normalized + sorted + de-duplicated."""
    hits = {
        _normalize(path)
        for path in changed_files or []
        if _is_ci_supplychain([path])
    }
    return sorted(hits)


#: The working-tree content reader the ack CLI uses pre-F6. Re-exported under the
#: name its callers already know; the implementation is shared with the committed
#: reader so both sides of the write-then-verify seam hash identically.
worktree_reader = worktree_bytes_reader


def ci_supplychain_fingerprint(changed_files, content_reader) -> str:
    """Fingerprint over the CI-boundary paths AND their content.

    Path-only binding was the first design and it was too weak: the path set is
    unchanged when an author acks "adds a ruff step" and then, before committing,
    edits the same workflow to add `pull_request_target:` and echo a secret. The
    recorded sentence would still license it. Hashing content means any edit to a
    CI file after the ack invalidates it — re-recording is the correct cost.

    Only CI paths are covered, so the finalization churn (compliance regen, events
    log, changelog drops) never perturbs it. Hashing rules are in
    :func:`~.git_blob_read.content_fingerprint`.
    """
    return content_fingerprint(_ci_paths(changed_files), content_reader)


def _validate_fields(ack: dict) -> str | None:
    """Return a human-readable reason the ack is invalid, or ``None`` if it is."""
    ref = ack.get("consistent_with")
    stmt = ack.get("statement")
    if not isinstance(ref, str) or len(ref.strip()) < _MIN_REF_CHARS:
        return "`consistent_with` is missing or empty"
    if not _DECISION_REF_RE.search(ref):
        return (
            f"`consistent_with` ({ref.strip()[:60]!r}) names no recorded decision — "
            "reference an ADR-NNN, an iterate-YYYY-MM-DD-slug run id, or #NNN"
        )
    if not isinstance(stmt, str) or len(stmt.strip()) < _MIN_STATEMENT_CHARS:
        return (
            f"`statement` must say what the change does to the CI trust boundary "
            f"(at least {_MIN_STATEMENT_CHARS} characters)"
        )
    if len(stmt.split()) < _MIN_STATEMENT_WORDS:
        return (
            f"`statement` must be a sentence, not padding "
            f"(at least {_MIN_STATEMENT_WORDS} words)"
        )
    return None


def check_ci_supplychain_ack(
    project_root: Path, run_id: str, commit_hash: str = ""
) -> CheckResult:
    """Non-dodgeable ``touches_ci_supplychain`` gate.

    An iterate whose diff touches the CI trust boundary MUST carry an
    acknowledgement naming the recorded posture decision the change agrees with,
    at ``.shipwright/planning/iterate/<run_id>/ci_supplychain_ack.json`` (the
    legacy ``iterate_latest.ci_supplychain_ack`` key is still honoured under
    identical validation — see :mod:`ci_supplychain_ack_store`). The flag is
    RECOMPUTED from the diff (merge-base..HEAD), never an agent-reported value,
    and the ack must be bound to this run and this change set — so neither
    omitting a self-report nor reusing an old ack works.

    Applies at EVERY complexity on purpose: a one-line workflow edit is still a
    trust-boundary change, and a complexity floor would be the obvious way to dodge
    it. This gate was the first to take that posture; the ``cross_component`` gate
    carried a medium+ floor until iterate-2026-08-01-coverage-gate-recompute-order,
    which cited the reasoning here and aligned it. The floors now agree — the only
    remaining complexity scope in the family is ``cross_layer_coverage``'s, and that
    one is a deliberate cost decision, not a dodge.

    Infra failures fail CLOSED at every complexity too: a gate that stands down when it
    cannot see is dodgeable by breaking its eyes. This was the last of the three
    ``git_context`` consumers on the binary ``rev-parse --git-dir`` probe (trg-20cc9ec8);
    those three agree now, while ``_git_available``'s five callers still carry the old
    conflation and are trg-4183acd3."""
    name = "CI supply-chain acknowledgement"
    # Tri-state, not "did git exit 0": a broken binary / `safe.directory` refusal /
    # permission failure / corrupt metadata / wedged index.lock all return non-zero from
    # INSIDE a repo, and reading that as "not a repo" green-SKIPped this gate on an infra
    # fault while printing "not a git repository" about a directory that was one. Only a
    # DEFINITIVE non-git answer stands it down (that SKIP keeps the CLI sandbox contract).
    ctx = git_context(project_root)
    if ctx == "not_git":
        return CheckResult(name, True, "skipped (not a git work tree)",
                           severity=Severity.SKIPPED.value)
    # Proceed only on an EXPLICIT work_tree: branching on `== "git_error"` and falling
    # through otherwise would make an unrecognised state fail OPEN, the one direction
    # this helper exists to prevent.
    if ctx != "work_tree":
        return CheckResult(
            name, False,
            "git could not answer whether this is a work tree — common causes: a wedged "
            "index.lock, a stalled filesystem, a `safe.directory` / dubious-ownership "
            "refusal, or git missing from PATH. Run `git -C <project> rev-parse "
            "--is-inside-work-tree` to see git's own message. Refusing to certify the "
            "CI trust boundary as untouched.")
    # An absent --commit, INSIDE a repo, is an unobtainable diff. Every sibling check
    # SKIPs here, which would make omitting one flag a total bypass of this gate —
    # the cheaper input must not be the safer one for a dodger. Resolve HEAD instead.
    commit = commit_hash
    if not commit:
        rc, out, _ = _run_git(project_root, "rev-parse", "HEAD")
        commit = out.strip() if rc == 0 else ""
    if not commit:
        return CheckResult(
            name, False,
            "no commit supplied and HEAD is unresolvable — refusing to certify "
            "the CI trust boundary as untouched",
        )
    changed = _iterate_changed_paths(project_root, commit)
    # `is None`, not `not changed`. The branch-view helper now signals ignorance as
    # None, so `[]` means one thing only: this branch has no net change vs the trunk.
    # Refusing on that would hard-FAIL a commit-then-revert branch with a message
    # naming a cause that did not occur and no remedy that clears it. Ignorance still
    # refuses — that posture is deliberate here and stricter than the sibling gates'.
    if changed is None:
        return CheckResult(
            name, False,
            f"cannot obtain the diff for {commit[:8]} — refusing to certify "
            "the CI trust boundary as untouched",
        )
    hit = _ci_paths(changed)
    if not hit:
        return CheckResult(name, True, "no CI supply-chain file touched")

    shown = ", ".join(hit[:3])
    # AFTER the no-CI-file early exit on purpose: the run id only becomes a path
    # component once an ack is actually required, so an odd run id on an unrelated
    # diff must not manufacture a finding. When one IS required, an unusable run id
    # means the ack cannot be located at all — fail closed rather than fall through
    # to the legacy key, which would make a malformed run id a bypass.
    if not is_safe_run_id(run_id):
        return CheckResult(
            name, False,
            f"CI supply-chain change touched ({shown}) but the run id "
            f"({str(run_id)[:60]!r}) is not a single safe path component, so the "
            "acknowledgement cannot be located",
        )
    ack, err, source = load_ack(project_root, run_id, commit)
    if err:
        return CheckResult(name, False, f"CI supply-chain change touched ({shown}) but {err}")
    if not ack:
        return CheckResult(
            name, False,
            f"CI supply-chain change touched ({shown}) but no acknowledgement was "
            f"recorded at {ack_relpath(run_id)} — run "
            "`shared/scripts/tools/record_ci_supplychain_ack.py` naming the "
            "recorded decision this change is consistent with",
        )

    ack_run = str(ack.get("run_id", "")).strip()
    if ack_run != run_id:
        return CheckResult(
            name, False,
            f"CI supply-chain change touched ({shown}) but the acknowledgement "
            f"belongs to another run ({ack_run or 'unset'!r} != {run_id!r}) — a "
            "stale ack cannot license this change",
        )

    try:
        expected = ci_supplychain_fingerprint(
            changed, committed_bytes_reader(project_root, commit))
    except GitReadError as exc:
        # A read failure must never be hashed as "<absent>" — that is the value a
        # genuinely DELETED path gets, so an ack recorded against a deletion would
        # license arbitrary content here (Stage-2 review).
        return CheckResult(
            name, False,
            f"CI supply-chain change touched ({shown}) but its content could not "
            f"be read from {commit[:8]} ({exc}) — refusing to certify a "
            "fingerprint over content this check could not see",
        )
    if str(ack.get("paths_fingerprint", "")).strip() != expected:
        return CheckResult(
            name, False,
            f"CI supply-chain change touched ({shown}) but the acknowledgement's "
            "paths_fingerprint does not match this diff — it was recorded for a "
            "different set of CI files, so it cannot license this one",
        )

    invalid = _validate_fields(ack)
    if invalid:
        return CheckResult(name, False, f"CI supply-chain acknowledgement is not usable: {invalid}")

    # Name the source. A worktree read means the ack is NOT in the commit and so
    # will not ship in the PR; the gate still passes (the record exists and is
    # correctly bound), but reporting it keeps "recorded" from silently reading as
    # "recorded and durable" — the ambiguity this whole change removes elsewhere.
    # Rendered next to the code that MINTS the vocabulary, because minting and
    # rendering it in two files is how `legacy-worktree` lost its caveat once.
    return CheckResult(
        name, True,
        f"CI supply-chain change acknowledged ({shown}) as consistent with "
        f"{str(ack['consistent_with']).strip()[:60]}{source_caveat(source)}",
    )
