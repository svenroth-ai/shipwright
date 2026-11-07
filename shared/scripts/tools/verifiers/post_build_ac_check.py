"""F11 claim check: the spec-reviewer's per-AC verdicts on the promises this run froze (Q2, phase 1 - a warning, never a hold).

Q1 records, before the build, each promise the run adds, changes, restores or exempts. This check reads those claims back
from the COMMITTED record (:mod:`lib.ac_claims`, code only) and the ``ac_verdicts`` the ``spec`` review row carries
(:mod:`lib.ac_verdicts`) and reports what is wrong, in plain words:

* **No AC review ran** (no ``spec`` row, one that did not run, or a completed one with no ``ac_verdicts``): said visibly
  with the claims it leaves unchecked - never a silent pass. At small complexity the cascade may not run at all.
* A claim with no verdict, a ``diverges`` (with the diff line the reviewer cited) and a ``weakens`` on a changed promise.
  A divergence on an item an operator confirmed or code decided is marked reject-grade; on an unconfirmed ``auto``
  assignment it is marked warning only. Both are WARNINGS here: nothing in this phase refuses anything.
* No record, or a record with no item: passes. Mode ``off`` (Q1's marker or setting), no event, a non-iterate source, an
  unseen branch or a catalog the parser cannot read: SKIPPED.
* Malformed record or review data never crashes the check and never turns F11 red: it is a WARNING.

The reviewer is an AI: a ``diverges`` is evidence for a person, not proof. Advisory and strict-exempt, like the other
iterate-local claims. Not a PR check.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_catalog import load_catalog  # noqa: E402
from lib.ac_claims import build_claims, judge  # noqa: E402
from lib.ac_mode import read_marker, resolve_mode, source_label  # noqa: E402
from lib.ac_surface import merge_base, read_blobs  # noqa: E402

from .affected_acs_check import _work_event  # noqa: E402
from .common import CheckResult, Severity  # noqa: E402
from .git_helpers import _branch_base_commit  # noqa: E402

CHECK_NAME = "post-build AC review (per-AC verdicts)"


def _warn(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, False, detail, severity=Severity.WARNING.value, strict_exempt=True)


def _skip(why: str) -> CheckResult:
    return CheckResult(CHECK_NAME, True, f"skipped ({why})", severity=Severity.SKIPPED.value)


def _spec_row(root: Path, run_id: str, commit_hash: str) -> dict:
    """The run's ``spec`` review row at the commit (``reviews.spec``, else the legacy ``gates.spec``); ``{}`` when absent or unreadable."""
    rel = f".shipwright/planning/iterate/{run_id}/reviews.json"
    try:
        text = read_blobs(root, commit_hash, [rel])[rel] if commit_hash else (root / rel).read_text(encoding="utf-8")
        record = json.loads(text or "")
    except (OSError, ValueError, RuntimeError):
        return {}
    for section in ("reviews", "gates"):
        row = (record.get(section) or {}).get("spec") if isinstance(record, dict) and isinstance(record.get(section), dict) else None
        if isinstance(row, dict):
            return row
    return {}


def check_post_build_ac_review(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    root = Path(project_root)
    try:
        marker = read_marker(root, run_id, commit_hash)
        mode, source = (marker["mode"], marker.get("source") or "flag") if marker else resolve_mode(root)
        if mode == "off":
            return _skip(f"Q1 off: mode=off (source={source_label(source)})")
        event = _work_event(root, run_id)
        if event is None:
            return _skip(f"no work_completed event for {run_id}")
        if event.get("source") != "iterate":
            return _skip(f"source={event.get('source') or 'unknown'}, not an iterate event")
        base = _branch_base_commit(root, commit_hash) if commit_hash else None
        if not base:
            return _skip("branch not visible")
        fork = event.get("stack_base_ref")  # a stacked campaign unit: its own fork point
        if isinstance(fork, str) and fork.strip():
            try:
                base = merge_base(root, fork.strip(), commit_hash)
            except RuntimeError:
                pass
        if load_catalog(root, base)["unparsed"]:
            return _skip("the requirement catalog has text but no FR heading this check can read")
        claims = build_claims(root, run_id, base, commit_hash or None)["claims"]
        if not claims:
            return CheckResult(CHECK_NAME, True, "this run froze no AC item, so there is nothing to review per AC")
        row = _spec_row(root, run_id, commit_hash)
        problems = judge(claims, row.get("ac_verdicts") if row.get("status") == "completed" else None)
        if problems and problems[0].startswith("no AC review ran") and row.get("status") not in (None, "completed"):
            problems[0] += f" (the spec review was recorded {row.get('status')})"
    except Exception as exc:  # noqa: BLE001 - malformed record or review data must never turn F11 red
        return _warn(f"the per-AC review could not be checked ({type(exc).__name__}: {exc})")
    if problems:
        return _warn("; ".join(problems) + " - evidence for a person, not proof; nothing is held")
    return CheckResult(CHECK_NAME, True, f"{len(claims)} claim(s) reviewed per AC, all match the diff")
