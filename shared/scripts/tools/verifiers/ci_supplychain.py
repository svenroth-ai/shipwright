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
their content*. Without the run binding, a leftover ack in ``iterate_latest``
would satisfy the gate for any later CI change; without the content binding, an
author could acknowledge "adds a ruff step" and then slip `pull_request_target:`
into the same file before committing. Both were false-greens by construction —
the first caught by the external review of this iterate's plan, the second by its
code review.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _run_git  # noqa: E402
from .integration_coverage import _iterate_changed_paths  # noqa: E402

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


def worktree_reader(project_root: Path):
    """Content reader for the WORKING TREE — what the ack CLI sees pre-F6."""
    def read(rel: str) -> str | None:
        try:
            return (project_root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    return read


def commit_reader(project_root: Path, commit: str):
    """Content reader for a COMMITTED tree — what the F11 verifier sees."""
    def read(rel: str) -> str | None:
        rc, out, _ = _run_git(project_root, "show", f"{commit}:{rel}")
        return out if rc == 0 else None
    return read


def ci_supplychain_fingerprint(changed_files, content_reader) -> str:
    """Fingerprint over the CI-boundary paths AND their content.

    Path-only binding was the first design and it was too weak: the path set is
    unchanged when an author acks "adds a ruff step" and then, before committing,
    edits the same workflow to add `pull_request_target:` and echo a secret. The
    recorded sentence would still license it. Hashing content means any edit to a
    CI file after the ack invalidates it — re-recording is the correct cost.

    Only CI paths are covered, so the finalization churn (compliance regen, events
    log, changelog drops) never perturbs it; a deleted file hashes as a sentinel so
    removing a security workflow is a distinct fingerprint, not an absent one.
    """
    parts = []
    for rel in _ci_paths(changed_files):
        body = content_reader(rel)
        if body is None:
            digest = "<absent>"
        else:
            digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        parts.append(rel + "\t" + digest)
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()


def _read_ack(project_root: Path, commit: str = "") -> tuple[dict | None, str | None]:
    """Return ``(ack, error)`` — ``error`` set means the results file is unusable.

    Prefers the COMMITTED copy: the ack is the durable record this gate exists to
    produce, and one that lives only in the working copy would never ship in the PR
    (same policy the events-log check enforces). Falls back to disk when the file is
    untracked at that commit.
    """
    raw: str | None = None
    if commit:
        rc, out, _ = _run_git(project_root, "show", f"{commit}:shipwright_test_results.json")
        if rc == 0:
            raw = out
    if raw is None:
        results_path = project_root / "shipwright_test_results.json"
        if not results_path.exists():
            return None, None
        try:
            raw = results_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            return None, f"shipwright_test_results.json is unreadable/corrupt ({exc})"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"shipwright_test_results.json is unreadable/corrupt ({exc})"
    if not isinstance(data, dict):
        return None, "shipwright_test_results.json is not a JSON object"
    latest = data.get("iterate_latest")
    if not isinstance(latest, dict):
        return None, None
    ack = latest.get("ci_supplychain_ack")
    return (ack if isinstance(ack, dict) else None), None


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

    An iterate whose diff touches the CI trust boundary MUST carry
    ``iterate_latest.ci_supplychain_ack`` naming the recorded posture decision the
    change agrees with. The flag is RECOMPUTED from the diff (merge-base..HEAD),
    never an agent-reported value, and the ack must be bound to this run and this
    change set — so neither omitting a self-report nor reusing an old ack works.

    Applies at EVERY complexity on purpose (unlike the ``cross_component`` gate's
    medium+ floor): a one-line workflow edit is still a trust-boundary change, and
    a complexity floor would be the obvious way to dodge it.
    """
    name = "CI supply-chain acknowledgement"
    # Not a git repository at all → SKIP. This is NOT the "diff unobtainable" case:
    # a real iterate always finalizes inside a repo, and running F11 outside one
    # leaves nothing to merge, so it is not a viable evasion path. Keeping it a SKIP
    # also preserves the sandbox contract the CLI tests rely on (a non-repo tmp dir
    # where every git-dependent check stands down).
    rc, _, _ = _run_git(project_root, "rev-parse", "--git-dir")
    if rc != 0:
        return CheckResult(name, True, "skipped (not a git repository)",
                           severity=Severity.SKIPPED.value)
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
    # `[]` reaches us from the merge-commit fallback (`git show --name-only` prints
    # no filenames for a merge), which is indistinguishable from "diff unavailable".
    if not changed:
        return CheckResult(
            name, False,
            f"cannot obtain the diff for {commit[:8]} — refusing to certify "
            "the CI trust boundary as untouched",
        )
    hit = _ci_paths(changed)
    if not hit:
        return CheckResult(name, True, "no CI supply-chain file touched")

    shown = ", ".join(hit[:3])
    ack, err = _read_ack(project_root, commit)
    if err:
        return CheckResult(name, False, f"CI supply-chain change touched ({shown}) but {err}")
    if not ack:
        return CheckResult(
            name, False,
            f"CI supply-chain change touched ({shown}) but no "
            "`iterate_latest.ci_supplychain_ack` was recorded — run "
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

    expected = ci_supplychain_fingerprint(changed, commit_reader(project_root, commit))
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

    return CheckResult(
        name, True,
        f"CI supply-chain change acknowledged ({shown}) as consistent with "
        f"{str(ack['consistent_with']).strip()[:60]}",
    )
