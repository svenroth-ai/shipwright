"""Per-unit review-diff attribution guard (campaign-dag-scheduler R3,
``.shipwright/planning/iterate/campaigns/campaign-dag-scheduler/sub-iterates/R3-review-diff-fix.md``).

Today (pre-R5a) every sub-iterate shares ONE worktree, so 3f-bis diffing
"the campaign worktree" is always the unit under review by construction.
R5a's wave-build flip gives every unit its OWN worktree — a review step
still hardcoded to "the campaign worktree" would then silently attribute
one unit's review to whatever unit was LAST checked out there. This module
makes that resolution explicit and per-unit now, so 3f-bis/3g already call
through it before R5a ships.

Three entry points, mirroring ``lib.unit_lease``'s pin/verify split plus a
ship step for the shipped-head field:

- :func:`pin` — resolves the unit's own ``worktree``/``branch`` from
  ``loop_state.json`` (falling back to the shared campaign worktree pre-R5a),
  asserts the checked-out branch matches, records ``HEAD`` as
  ``reviewed_head``, pins ``base_sha`` ONCE (never recomputed at verify
  time), and writes ``runs/{loop_id}/{unit_id}/a{attempt_id}/review_pin.json``
  plus a legacy ``.../reviewed_head`` file for 3g's existing check — that
  legacy file holds the SAME SHA only until 3f-bis's record commit
  overwrites it with the SHIPPED head. ``shipped_head`` starts ``None`` for
  a reviewed (non-``review_skipped``) unit; it stays ``None`` until
  :func:`ship` records it.
- :func:`ship` — records the pushed review-record-commit SHA into an
  existing pin's ``shipped_head`` field, after confirming it really is the
  branch's current tip. Called once, by 3f-bis, right after the
  ``reviews.json`` commit lands on the remote. A ``review_skipped`` unit
  never needs it: :func:`pin` already set ``shipped_head`` equal to
  ``reviewed_head`` for that case.
- :func:`verify` — asserts a pinned field is still the branch's actual tip:
  ``reviewed_head`` or ``shipped_head`` (exactly ``reviewed_head`` when
  ``review_skipped``, else exactly the recorded ``shipped_head``, one commit
  ahead of ``reviewed_head`` — the record commit; BLOCKS rather than falls
  back to a content-blind check if :func:`ship` was never called). This is
  the SINGLE detection path for every branch-*content* change route (rebase,
  force-push, manual push, a failed merge-time check). It does NOT detect a
  PR *base* retarget with the tip left unchanged — 3g still resolves the PR
  by branch name, not by the pinned ``pr_node_id``/``pr_base_ref`` fields
  (R3 doubt-round, low: those fields are recorded but intentionally
  write-only for now; the Stage-1-accepted rejected-alternative above is
  the same call for 3g's existing `head_pin` mechanism).

Unlike ``lib.unit_lease``'s warn-and-continue, a failure here is FATAL: an
unpinned or misattributed review is exactly the bug this module prevents, so
:class:`ReviewAttributionError` must propagate, never be swallowed.

External plan/code review dispositions are recorded in
``.shipwright/planning/adr/iterate-2026-09-22-r3-review-diff-fix-adr.md``;
per-hardening rationale lives beside its code (``_safe_segment``,
``resolve_unit_identity``, ``_run_git``), not restated here.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.atomic_write import durable_atomic_write, durable_read_text  # noqa: E402

#: Full-match hex-SHA check — `reviewed_head` flows into `git rev-list
#: --parents -n 1 {sha}` argv below; a value git would parse as an option
#: must never reach that call (same pattern as `lib.loop_state._SHA_RE`).
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

class ReviewAttributionError(RuntimeError):
    """Raised for any pin/verify failure — always fatal to the caller."""


def _safe_segment(name: str, value: str) -> str:
    """Reject a path segment that could escape `.shipwright/runs/` (blocks
    `.`/`..`, any separator, NUL, and `:` — a Windows drive-relative escape
    e.g. `D:evil`) while staying Unicode-permissive (non-ASCII `unit_id` is
    legitimate)."""
    if (not value or value in (".", "..") or "/" in value or "\\" in value
            or "\x00" in value or ":" in value):
        raise ReviewAttributionError(
            f"{name} {value!r} is not a safe path segment — refusing to build "
            "a runs/ path from it")
    return value


def _find_unit(state: dict, unit_id: str) -> dict | None:
    """Exact match first, case-folded fallback (``lib.unit_lease``'s own
    convention) — a resolve must find the same row either lookup style would."""
    units = state.get("units") or []
    for unit in units:
        if unit.get("id") == unit_id:
            return unit
    folded = str(unit_id).lower()
    for unit in units:
        if str(unit.get("id")).lower() == folded:
            return unit
    return None


def _check_loop_id(state: dict, loop_id: str) -> None:
    """Refuse a caller-supplied ``--loop-id`` that disagrees with the state
    file's own ``loop_id`` (R3 doubt-round, low) — ``--state``,
    ``--project-root``, ``--campaign-worktree``, and ``--loop-id`` are
    independent CLI args with nothing else cross-checking them; a pin landing
    under the wrong loop's `runs/` tree is exactly the kind of silent
    misattribution this module exists to prevent."""
    state_loop_id = state.get("loop_id")
    if state_loop_id and state_loop_id != loop_id:
        raise ReviewAttributionError(
            f"--loop-id {loop_id!r} does not match loop_state.json's own "
            f"loop_id {state_loop_id!r} — refusing to pin under the wrong loop")


def _resolve(state_path: Path | str, unit_id: str, *, loop_id: str, campaign_worktree: str) -> dict:
    """Load state, cross-check ``loop_id``, and resolve the unit's identity —
    the preamble shared by ``pin``/``verify``/``ship`` (code-review round 3,
    medium: extracted to stop the same four lines drifting apart across the
    three functions)."""
    state = json.loads(durable_read_text(Path(state_path), encoding="utf-8"))
    _check_loop_id(state, loop_id)
    return resolve_unit_identity(state, unit_id, campaign_worktree=campaign_worktree)


def _load_pin(pin_path: Path, canonical_id: str, unit_id: str, *, verb: str) -> dict:
    """Load and validate an existing pin file — shared by ``verify``/``ship``
    (code-review round 3, medium). ``verb`` names the caller in the error
    messages ("verify a mismatched pin" / "ship a mismatched pin")."""
    if not pin_path.exists():
        raise ReviewAttributionError(
            f"no pin file at {pin_path} — was pin() ever run for this unit/attempt?")
    try:
        pinned = json.loads(durable_read_text(pin_path, encoding="utf-8"))
        # A top-level JSON list/string/number can satisfy `"reviewed_head" not
        # in pinned` (e.g. `"reviewed_head" in "a reviewed_head string"`) and
        # then raise an uncaught AttributeError at `.get()` below instead of
        # the clean error this guard promises (doubt-round, round 2, low —
        # still fails closed either way, but the traceback was uncaught).
        if not isinstance(pinned, dict) or "reviewed_head" not in pinned:
            raise KeyError("reviewed_head")
    except (json.JSONDecodeError, KeyError) as exc:
        raise ReviewAttributionError(
            f"pin file at {pin_path} is malformed or missing 'reviewed_head': {exc}") from exc
    if pinned.get("unit_id") != canonical_id:
        raise ReviewAttributionError(
            f"pin file at {pin_path} belongs to unit {pinned.get('unit_id')!r}, "
            f"not {unit_id!r} — refusing to {verb} a mismatched pin")
    return pinned


def _single_parent(sha: str, *, cwd: str) -> str | None:
    """The ONE parent of ``sha``, or ``None`` if it has zero parents (a root
    commit) or more than one (a MERGE commit) — used by ``verify``/``ship``'s
    ancestry check. A bare ``rev-parse {sha}^`` resolves only the FIRST
    parent and never errors on a merge commit, so it could not tell a
    genuine single-commit record from a merge whose first parent happened to
    be ``reviewed_head`` (doubt-round, round 2, medium: this was the only
    thing distinguishing a real review-record commit from an arbitrary merge
    landed on the shared worktree, since ``diff_sha256`` is evidence, not a
    gate)."""
    if not _SHA_RE.match(sha):
        return None
    try:
        tokens = _run_git(["rev-list", "--parents", "-n", "1", sha], cwd=cwd).split()
    except ReviewAttributionError:
        return None
    return tokens[1] if len(tokens) == 2 else None


def _run_git(args: list[str], *, cwd: str, raw: bool = False) -> str | bytes:
    """Run git, returning stripped stdout text, or (``raw=True``) the exact
    stdout bytes — used for the diff body, whose sha256 must be stable
    across platforms/locales and must never itself raise a decode error on
    content this call isn't supposed to interpret, only hash. Text mode
    decodes as utf-8/replace (not the platform default, cp1252 on Windows):
    repo content already contains bytes outside cp1252 (curly quotes,
    em-dash), and an undecodable byte here must not surface as an uncaught
    UnicodeDecodeError instead of a clean ReviewAttributionError."""
    try:
        result = subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, timeout=30,
            **({} if raw else {"text": True, "encoding": "utf-8", "errors": "replace"}),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise ReviewAttributionError(f"git {' '.join(args)} in {cwd}: {exc}") from exc
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace") if raw else result.stderr
        raise ReviewAttributionError(f"git {' '.join(args)} in {cwd} failed: {stderr.strip()}")
    return result.stdout if raw else result.stdout.strip()


def resolve_unit_identity(state: dict, unit_id: str, *, campaign_worktree: str) -> dict:
    """``{worktree, branch, attempt_id}`` for a unit row.

    ``worktree`` falls back to ``campaign_worktree`` when the row carries no
    ``worktree`` field (every row, pre-R5a — see module docstring).
    ``attempt_id`` falls back to ``a{attempt}`` when absent (``lib.unit_lease``
    leaves it ``null`` until a later campaign wires real attempt-passing —
    R3's spec names this exact default).
    """
    unit = _find_unit(state, unit_id)
    if unit is None:
        raise ReviewAttributionError(f"unit {unit_id!r} not found in loop_state")
    worktree = unit.get("worktree") or campaign_worktree
    branch = unit.get("branch")
    if not branch:
        raise ReviewAttributionError(f"unit {unit_id!r} has no branch recorded in loop_state")
    attempt = unit.get("attempt")
    if not isinstance(attempt, int) or isinstance(attempt, bool):
        attempt = 0
    attempt_id = unit.get("attempt_id") or f"a{attempt}"
    # The row's OWN spelling of `id`, not the caller's — `_find_unit` resolves
    # case-insensitively, so a caller spelling "Unit-A" against a row stored
    # as "unit-a" must not round-trip its own casing into the pin file, or a
    # later verify() call spelled like the row (or vice versa) would see two
    # different `unit_id` strings and fail the mismatch cross-check on a
    # legitimate pin (external plan review, glm, medium).
    canonical_id = unit.get("id")
    return {
        "worktree": worktree, "branch": branch, "attempt_id": attempt_id,
        "unit_id": canonical_id,
    }


def _pin_dir(loop_id: str, unit_id: str, attempt_id: str, *, project_root: str) -> Path:
    loop_id = _safe_segment("loop_id", loop_id)
    unit_id = _safe_segment("unit_id", str(unit_id))
    attempt_id = _safe_segment("attempt_id", str(attempt_id))
    return Path(project_root) / ".shipwright" / "runs" / loop_id / unit_id / attempt_id


def _legacy_reviewed_head_path(loop_id: str, unit_id: str, *, project_root: str) -> Path:
    loop_id = _safe_segment("loop_id", loop_id)
    unit_id = _safe_segment("unit_id", str(unit_id))
    return Path(project_root) / ".shipwright" / "runs" / loop_id / unit_id / "reviewed_head"


def pin(
    state_path: Path | str,
    unit_id: str,
    *,
    project_root: str,
    campaign_worktree: str,
    loop_id: str,
    default_branch: str = "main",
    review_skipped: bool = False,
    pr_node_id: str | None = None,
    pr_head_ref: str | None = None,
    pr_base_ref: str | None = None,
    now: str | None = None,
) -> dict:
    """Pin the reviewed diff for ``unit_id``. See module docstring.

    Raises :class:`ReviewAttributionError` if the unit is unknown, has no
    recorded branch, or its resolved worktree does not have that branch
    checked out (refusing to pin the wrong branch's diff is the whole point).
    """
    identity = _resolve(state_path, unit_id, loop_id=loop_id, campaign_worktree=campaign_worktree)
    worktree, branch, attempt_id = identity["worktree"], identity["branch"], identity["attempt_id"]
    canonical_id = identity["unit_id"]

    checked_out = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree)
    if checked_out != branch:
        raise ReviewAttributionError(
            f"unit {unit_id!r} expects branch {branch!r} checked out at {worktree}, "
            f"found {checked_out!r} — refusing to pin the wrong branch's diff")

    reviewed_head = _run_git(["rev-parse", "HEAD"], cwd=worktree)
    base_sha = _run_git(["merge-base", f"origin/{default_branch}", "HEAD"], cwd=worktree)
    # Hashed as raw bytes, not decoded text: the diff body is evidence, not
    # data this call needs to interpret, and a byte hash is stable across
    # platforms/locales where a decode/re-encode round trip would not be.
    diff_bytes = _run_git(["diff", f"{base_sha}...{reviewed_head}"], cwd=worktree, raw=True)
    diff_sha256 = hashlib.sha256(diff_bytes).hexdigest()
    shipped_head = reviewed_head if review_skipped else None
    pinned_at = now if now is not None else datetime.now(timezone.utc).isoformat()

    payload = {
        "unit_id": canonical_id,
        "attempt_id": attempt_id,
        "branch": branch,
        "worktree": str(worktree),
        "reviewed_head": reviewed_head,
        "base_sha": base_sha,
        "diff_sha256": diff_sha256,
        "shipped_head": shipped_head,
        "pinned_at": pinned_at,
        "review_skipped": review_skipped,
        "pr_node_id": pr_node_id,
        "pr_head_ref": pr_head_ref,
        "pr_base_ref": pr_base_ref,
    }

    pin_dir = _pin_dir(loop_id, canonical_id, attempt_id, project_root=project_root)
    pin_dir.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(
        pin_dir / "review_pin.json", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")

    legacy_path = _legacy_reviewed_head_path(loop_id, canonical_id, project_root=project_root)
    legacy_path.parent.mkdir(parents=True, exist_ok=True)
    durable_atomic_write(legacy_path, reviewed_head + "\n")

    return payload


def verify(
    state_path: Path | str,
    unit_id: str,
    *,
    project_root: str,
    campaign_worktree: str,
    loop_id: str,
    against: str,
    expect_file: str = "review_pin.json",
) -> dict:
    """Verify a pinned field is still the branch's actual tip. ``against`` is
    ``"reviewed_head"`` or ``"shipped_head"``. Returns
    ``{ok, detail, current_tip, pin}`` — ``ok`` is the caller's ALLOW/BLOCK
    decision; this never raises for a legitimate mismatch, only for a
    structural failure (unknown unit, missing pin file, git failure).
    """
    if against not in ("reviewed_head", "shipped_head"):
        raise ReviewAttributionError(
            f"--against must be 'reviewed_head' or 'shipped_head', got {against!r}")

    identity = _resolve(state_path, unit_id, loop_id=loop_id, campaign_worktree=campaign_worktree)
    worktree, branch, attempt_id = identity["worktree"], identity["branch"], identity["attempt_id"]
    canonical_id = identity["unit_id"]

    pin_path = _pin_dir(loop_id, canonical_id, attempt_id, project_root=project_root) / expect_file
    pinned = _load_pin(pin_path, canonical_id, unit_id, verb="verify")

    # Fully qualified ref: a bare `branch` name is resolved against tags
    # before refs/heads/ (gitrevisions precedence), so a tag sharing the
    # branch's name would silently win here; qualifying also closes the
    # option-injection route for a `branch` value beginning with `-`.
    current_tip = _run_git(["rev-parse", "--verify", f"refs/heads/{branch}"], cwd=worktree)

    if against == "reviewed_head":
        ok = current_tip == pinned["reviewed_head"]
        detail = (f"branch {branch!r} tip {current_tip} vs pinned "
                  f"reviewed_head {pinned['reviewed_head']}")
    else:
        recorded_shipped = pinned.get("shipped_head")
        if pinned.get("review_skipped"):
            ok = current_tip == pinned["reviewed_head"]
            detail = (f"review_skipped: branch tip {current_tip} vs pinned "
                      f"reviewed_head {pinned['reviewed_head']}")
        elif current_tip == pinned["reviewed_head"]:
            ok = False
            detail = (f"branch tip {current_tip} equals pinned reviewed_head "
                      "— no review-record commit on top of reviewed_head")
        elif recorded_shipped is None:
            # R3 doubt-round, high: a reviewed (non-skipped) pin's
            # shipped_head stays None until ship() records it. Falling back
            # to "any commit whose parent is reviewed_head" here would be
            # content-blind — indistinguishable from a force-push/amend that
            # replaced the actual review-record commit with something else
            # entirely, which is precisely the case this check exists to
            # catch. Refuse to ALLOW instead of guessing.
            ok = False
            detail = (f"branch tip {current_tip} has moved past pinned reviewed_head "
                      f"{pinned['reviewed_head']} but shipped_head was never recorded "
                      "(ship() not called) — refusing to fall back to a content-blind check")
        elif current_tip != recorded_shipped:
            ok = False
            detail = (f"branch tip {current_tip} does not match pinned shipped_head "
                      f"{recorded_shipped} — branch moved after shipping (force-push, "
                      "amend, or an extra commit)")
        else:
            parent = _single_parent(current_tip, cwd=worktree)
            ok = parent is not None and parent == pinned["reviewed_head"]
            detail = (f"branch tip {current_tip} (pinned shipped_head) parent {parent} "
                      f"vs pinned reviewed_head {pinned['reviewed_head']}")

    return {"ok": ok, "detail": detail, "current_tip": current_tip, "pin": pinned}


def ship(
    state_path: Path | str,
    unit_id: str,
    *,
    project_root: str,
    campaign_worktree: str,
    loop_id: str,
    shipped_head: str,
) -> dict:
    """Record the pushed review-record-commit SHA into an existing pin's
    ``shipped_head`` field (R3 doubt-round, high). Call once, right after
    3f-bis's ``reviews.json`` commit lands on the remote — before this call,
    a reviewed (non-skipped) unit's ``shipped_head`` stays ``None``, and
    ``verify(against="shipped_head")`` refuses to ALLOW rather than fall back
    to a content-blind check.

    Raises :class:`ReviewAttributionError` if no pin exists yet, ``unit_id``
    resolves to a different pin, ``shipped_head`` is not the branch's actual
    current local tip (refusing to record a SHA that isn't even checked out
    locally — the campaign path pushes before calling this, so in practice
    it is also the pushed SHA, but this check only sees the local ref), the
    pin was already shipped with a DIFFERENT head (a retry must not silently
    overwrite a prior ship), or (unless ``review_skipped``) ``shipped_head``
    is not EXACTLY one commit ahead of the pinned ``reviewed_head`` — the
    same ancestry requirement ``verify(against="shipped_head")`` enforces
    (code-review round 3, high: this was the only gap, since today's
    3f-bis/3g call `ship`, never `verify`, so an unchecked `ship` would have
    been the sole thing standing between an unreviewed extra commit and a
    merge).
    """
    if not _SHA_RE.match(shipped_head):
        raise ReviewAttributionError(f"shipped_head {shipped_head!r} is not a 40-hex SHA")

    identity = _resolve(state_path, unit_id, loop_id=loop_id, campaign_worktree=campaign_worktree)
    worktree, branch, attempt_id = identity["worktree"], identity["branch"], identity["attempt_id"]
    canonical_id = identity["unit_id"]

    pin_path = _pin_dir(loop_id, canonical_id, attempt_id, project_root=project_root) / "review_pin.json"
    pinned = _load_pin(pin_path, canonical_id, unit_id, verb="ship")

    current_tip = _run_git(["rev-parse", "--verify", f"refs/heads/{branch}"], cwd=worktree)
    if current_tip != shipped_head:
        raise ReviewAttributionError(
            f"shipped_head {shipped_head} is not branch {branch!r}'s current local "
            f"tip ({current_tip}) at {worktree} — refusing to record a SHA that "
            "isn't even checked out on this branch")

    # Checked before the ancestry requirement below: a retry that ships a
    # SECOND, different head is refused for being a silent overwrite, not
    # (also, confusingly) for failing an ancestry check that a legitimate
    # re-pin + re-ship would have made moot anyway.
    existing = pinned.get("shipped_head")
    if existing is not None and existing != shipped_head:
        raise ReviewAttributionError(
            f"pin at {pin_path} already has shipped_head {existing} — refusing to "
            f"overwrite with {shipped_head} (a re-ship after retry must not be silent)")

    if not pinned.get("review_skipped"):
        parent = _single_parent(shipped_head, cwd=worktree)
        if parent != pinned["reviewed_head"]:
            raise ReviewAttributionError(
                f"shipped_head {shipped_head}'s parent {parent} does not equal "
                f"pinned reviewed_head {pinned['reviewed_head']} — shipped_head "
                "must be exactly one commit (the review-record commit) ahead of "
                "reviewed_head, and that commit must not be a merge; re-pin and "
                "re-review before shipping")

    pinned["shipped_head"] = shipped_head
    durable_atomic_write(pin_path, json.dumps(pinned, indent=2, ensure_ascii=False) + "\n")
    return pinned
