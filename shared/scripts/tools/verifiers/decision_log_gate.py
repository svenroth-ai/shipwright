"""ADR / decision-log integrity checks for the iterate F11 verifier.

Extracted from ``iterate_checks.py``
(iterate-2026-07-20-runner-finalization-integrity) so that load-bearing
verifier stays under its bloat ceiling. ``iterate_checks`` re-exports the two
public checks (``check_adr_in_iterate_history``,
``check_iterate_no_direct_decision_log``) plus the ``_drop_carries_adr`` helper,
so every existing import path — ``run_all_checks``, the
``verify_iterate_finalization`` wrapper, and the tests — keeps resolving.

Together the two checks enforce that an iterate records its ADR as a
decision-DROP keyed by ``run_id`` and NEVER appends to ``decision_log.md``
directly (the ``ADR-NNN`` is assigned only at ``/shipwright-changelog`` release
time by ``aggregate_decisions.py``).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.events_log import resolve_main_repo_root  # noqa: E402
from lib.iterate_entry import (  # noqa: E402
    find_entry_by_run_id,
    sanitize_run_id_for_filename,
)

from .common import CheckResult, Severity  # noqa: E402
from .integration_coverage import _iterate_changed_paths  # noqa: E402


def _drop_carries_adr(drop_dir: Path, run_id: str) -> bool:
    """True iff a decision-drop for ``run_id`` exists AND actually carries the
    ADR: it parses as a JSON object, its ``run_id`` field matches, and its
    ``decision`` field is non-empty.

    "The drop actually exists" (F11 contract) must mean "the drop has the ADR".
    A bare/placeholder ``{}`` file — the shape left behind when the per-run ADR
    was silently lost — is NOT sufficient: it would let a run whose ADR vanished
    still read green. ``write_decision_drop.py`` always writes ``run_id`` and a
    non-empty ``decision`` (it refuses an empty decision at write time), so a
    real drop always satisfies this; only lost/placeholder content fails.
    """
    if not drop_dir.is_dir():
        return False
    safe = sanitize_run_id_for_filename(run_id)
    for p in drop_dir.glob(f"{safe}_*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if (
            isinstance(data, dict)
            and data.get("run_id") == run_id
            and str(data.get("decision", "")).strip()
        ):
            return True
    return False


def check_adr_in_iterate_history(project_root: Path, run_id: str) -> CheckResult:
    """F3 + F5c consistency — the entry for ``run_id`` carries an ``adr`` field
    that resolves to a real ADR.

    Two ADR-identity shapes are accepted:

    - ``ADR-NNN`` — a numbered ADR; must be a heading in ``decision_log.md``
      (the direct-append path used by non-iterate phases).
    - a run-id — the iterate decision-drop pattern (H). Pre-aggregation the
      ADR lives as a JSON drop under ``decision-drops/``; post-aggregation it
      has been folded into ``decision_log.md`` with a ``Run-ID:`` line.

    Entry lookup goes through the merged reader so new-format projects
    without any legacy array still resolve cleanly.
    """
    name = "ADR recorded + present"
    entry = find_entry_by_run_id(project_root, run_id)
    if not entry:
        return CheckResult(name, False, f"run_id={run_id} not in iterate history")
    adr_id = entry.get("adr")
    if not adr_id:
        return CheckResult(name, False, f"iterate_history[{run_id}].adr missing")

    log = project_root / ".shipwright" / "agent_docs" / "decision_log.md"
    log_content = (
        log.read_text(encoding="utf-8", errors="ignore") if log.exists() else ""
    )

    # Run-id ADR identity — the H decision-drop pattern. fullmatch (not
    # match) so a run-id that merely starts with "adr-" is not misread as a
    # numbered ADR.
    if not re.fullmatch(r"(?i)ADR-\d+", adr_id.strip()):
        # Worktree-aware: iterate F3 writes the decision-drop next to the
        # MAIN repo (write_decision_drop.drop_dir), but this verifier runs
        # at F11 with project_root = the iterate worktree. Resolve the drop
        # dir against the main repo, or the pending-drop branch never
        # matches and a freshly-written ADR is reported missing.
        drop_root = resolve_main_repo_root(project_root) or project_root
        drop_dir = drop_root / ".shipwright" / "agent_docs" / "decision-drops"
        # Accept run-id ADR identity ONLY when the drop actually CARRIES the ADR
        # (parses + run_id match + non-empty decision) OR a matching Run-ID line
        # is present in decision_log.md. An empty/placeholder drop no longer
        # passes — that is the shape of a silently-lost ADR.
        if _drop_carries_adr(drop_dir, adr_id):
            return CheckResult(
                name, True,
                f"{adr_id}: decision-drop carries the ADR (pending aggregation)",
            )
        if log_content and re.search(
            rf"\*\*Run-ID:\*\*\s*{re.escape(adr_id)}\b", log_content
        ):
            return CheckResult(
                name, True, f"{adr_id}: ADR aggregated into decision_log.md"
            )
        return CheckResult(
            name, False,
            f"{adr_id}: no decision-drop carrying the ADR and no Run-ID line in "
            "decision_log.md",
        )

    # Numbered ADR — heading must be present in decision_log.md.
    if not log.exists():
        return CheckResult(name, False, f"missing {log.name}")
    if re.search(rf"### {re.escape(adr_id)}[: ]", log_content):
        return CheckResult(name, True, f"{adr_id} present in decision_log.md")
    return CheckResult(name, False, f"{adr_id} NOT found in decision_log.md")


def _is_decision_log_path(path: str) -> bool:
    """True for the tracked agent-doc ``.shipwright/agent_docs/decision_log.md``
    (any separator). Scoped to that exact path — tool scripts, tests, and
    fixtures that merely mention ``decision_log`` are not matched."""
    norm = path.replace("\\", "/")
    return norm == ".shipwright/agent_docs/decision_log.md" or norm.endswith(
        "/.shipwright/agent_docs/decision_log.md"
    )


def check_iterate_no_direct_decision_log(
    project_root: Path,
    run_id: str,
    commit_hash: str,
) -> CheckResult:
    """Diff-driven gate — an iterate NEVER writes ``decision_log.md`` directly.

    Iterate F3 writes a decision-DROP keyed by ``run_id``; the sequential
    ``ADR-NNN`` is assigned at exactly one serialized point — ``/shipwright-changelog``
    release time (``aggregate_decisions.py``). Two parallel iterates each
    appending to ``decision_log.md`` would both compute ``max(ADR)+1`` in their
    own worktree and silently collide on the number — the exact race
    ``write_decision_drop.py`` exists to prevent. This gate RECOMPUTES the touched
    paths from the iterate's own changes (``merge-base..HEAD``, same view as the
    ``cross_component`` gate), so it cannot be dodged by omitting a self-report,
    and FAILS closed (ERROR) if the iterate modified
    ``.shipwright/agent_docs/decision_log.md``.

    SKIP when git is unavailable, no ``--commit`` is supplied, or the diff can't
    be read. The release-time aggregation write is a ``/shipwright-changelog``
    commit, not an iterate commit — this iterate verifier never runs against it,
    so the legitimate producer is not affected. Origin:
    iterate-2026-07-20-runner-finalization-integrity.
    """
    name = "no direct decision_log.md write (iterate)"
    if not commit_hash:
        return CheckResult(
            name, True, "skipped (no --commit supplied)",
            severity=Severity.SKIPPED.value,
        )
    changed = _iterate_changed_paths(project_root, commit_hash)
    if changed is None:
        return CheckResult(
            name, True, "skipped (git unavailable / no diff)",
            severity=Severity.SKIPPED.value,
        )
    hits = [p for p in changed if _is_decision_log_path(p)]
    if hits:
        return CheckResult(
            name, False,
            f"iterate modified {hits[0]} directly — an iterate must record its "
            "ADR as a decision-DROP (write_decision_drop.py, F3), NOT append to "
            "decision_log.md; the ADR-NNN is assigned at /shipwright-changelog "
            "release time. Revert the decision_log.md edit and write the drop.",
        )
    return CheckResult(name, True, "decision_log.md not modified by this iterate")
