"""``depends_on`` schema validators + the resume-safe status projector.

Campaign ``campaign-dag-scheduler`` R1
(``.shipwright/planning/iterate/2026-09-20-campaign-dag-scheduler-plan.md``).
Split out of ``campaign_status.py`` (already at its own 300-line bloat limit
with no baseline entry — a first crossing lands as an unplanned Group H
detective finding post-merge) rather than folded in: these three validators
plus :func:`safe_project_campaign_status` are a coherent, independently
testable unit, and living together means `safe_project_campaign_status`'s
signature can genuinely mirror ``regenerate_campaign_status``'s
``tuple[dict, dict]`` return without a new shape the existing
``campaign_progress.py`` caller can't consume.

Import convention: this module (and the sibling ``loop_state.py`` /
``loop_claim.py`` R4 adds) is always imported as ``lib.campaign_graph`` —
matching ``campaign_status.py``, ``worktree_location.py``, and
``campaign_session_lock.py`` — **never** as a bare sibling import the way
``autonomous_loop.py`` imports ``branch_base``/``file_lock`` today. Two
module objects for one file is the ADR-045 lib-collision class, and it would
silently break the module-object monkeypatching this plan's test strategy
relies on for the diff-coverage gate.

``validate_dependency_graph`` returns a flat ``list[str]``, each entry
prefixed ``"structural: "`` or ``"charset: "`` — a plain-string finding list
keeps the function's stated return type exact while still letting a caller
partition by severity with ``msg.startswith("charset:")``: structural
findings (duplicate/missing/self-loop/cycle) are always a hard reject
everywhere; a charset finding's severity is caller-controlled
(``campaign_init.py`` hard-rejects it too; ``safe_project_campaign_status``
below only warns).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from lib.campaign_status import parse_campaign_skeleton, project_campaign_status, slug_from_md

#: `[A-Za-z0-9._-]`, bounded to 64 chars. No leading/trailing separator, no
#: `..` segment, no literal `--` (reserved as the campaign-slug/unit-id path
#: separator — see R2's per-unit worktree naming).
_ID_CHARSET_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_SEPARATOR_CHARS = "._-"


def id_charset_ok(value: str) -> bool:
    """``True`` iff `value` is a safe campaign sub-iterate / dependency id.

    Verified against ``R0``, ``15.0``, ``14.2``, ``p3.8`` (all pass) — the
    real id shapes this campaign's own sub-iterates use.
    """
    if not isinstance(value, str) or not value:
        return False
    if not _ID_CHARSET_RE.match(value):
        return False
    if value[0] in _SEPARATOR_CHARS or value[-1] in _SEPARATOR_CHARS:
        return False
    if ".." in value or "--" in value:
        return False
    return True


def validate_dependency_graph(rows: list[dict]) -> list[str]:
    """Pure, structural validation of a campaign's ``depends_on`` graph.

    `rows` is the ``parse_campaign_skeleton`` shape: each a dict with at
    least ``id`` and ``depends_on`` (a list of bare ids). Checks duplicate
    ids, every referenced id exists, no self-dependency, no cycle (any
    length) — all structural, always a hard error — plus a charset check
    (see module docstring for the severity-partitioning convention).

    **Case-insensitive throughout** (external plan review AND external code
    review, all three reviewer passes converged on this): Windows worktree
    directories case-fold, so ``R0`` and ``r0`` would collide on disk (R2's
    per-unit worktree naming) despite each passing the charset check
    independently — duplicate detection, dependency existence, AND cycle
    detection all fold case (the cycle-detection adjacency graph itself is
    keyed/traversed by case-folded id, not just the existence check — a code
    review round found that a mixed-case cycle such as ``R0 -> b``, ``B ->
    r0`` escaped the original exact-case adjacency, and the original-case
    display was resolved back afterward for messages). The ORIGINAL
    (author-supplied) casing is kept in every message. A row with a missing
    or non-string ``id`` is its own structural finding and is excluded from
    the rest of this function's id-keyed set/sort operations (a mixed
    ``str``/non-``str`` id set previously reached a bare ``sorted()`` and
    raised ``TypeError`` before any finding was returned — a code-review
    finding).
    """
    findings: list[str] = []

    valid_rows = [r for r in rows if isinstance(r.get("id"), str) and r.get("id")]
    if len(valid_rows) != len(rows):
        findings.append(
            "structural: row(s) missing a valid (non-empty, string) id — "
            "cannot validate a dependency graph without one"
        )
    rows = valid_rows

    ids = [r["id"] for r in rows]
    id_set_lower = {i.lower() for i in ids}
    lower_to_original: dict[str, str] = {}
    for i in ids:
        lower_to_original.setdefault(i.lower(), i)

    dupes_exact = sorted({i for i in ids if ids.count(i) > 1})
    lower_counts: dict[str, list] = {}
    for i in ids:
        lower_counts.setdefault(i.lower(), []).append(i)
    dupes_case_fold = sorted(
        {tuple(sorted(set(v))) for v in lower_counts.values() if len(set(v)) > 1}
    )
    if dupes_exact:
        findings.append(f"structural: duplicate sub-iterate id(s): {dupes_exact}")
    if dupes_case_fold:
        findings.append(
            f"structural: sub-iterate id(s) collide when case-folded "
            f"(Windows worktree paths are case-insensitive): {dupes_case_fold}"
        )

    adjacency: dict[str, list[str]] = {}
    for row in rows:
        rid = row["id"]
        rid_l = rid.lower()
        deps = list(row.get("depends_on") or [])
        cycle_edges = []  # self-loops excluded here — reported once, below, not double-counted as a cycle
        for dep in deps:
            dep_l = str(dep).lower()
            if dep_l == rid_l:
                findings.append(f"structural: unit {rid!r} depends on itself")
            else:
                if dep_l not in id_set_lower:
                    findings.append(f"structural: unit {rid!r} depends on unknown id {dep!r}")
                cycle_edges.append(dep_l)  # case-folded — matches adjacency's own keys
        adjacency[rid_l] = cycle_edges

    cyclic = _find_cycle_members(adjacency)
    if cyclic:
        cyclic_original = sorted({lower_to_original.get(c, c) for c in cyclic})
        findings.append(f"structural: dependency cycle involving id(s): {cyclic_original}")

    all_values = list(ids) + [d for row in rows for d in (row.get("depends_on") or [])]
    # Doubt review (low): `id_charset_ok` correctly returns False for a
    # non-str value, but `sorted()` over a mixed str/non-str set (e.g. a
    # stray int dep) raises TypeError — the same class of bug already fixed
    # for `ids` above (L93), missed here. Every production caller pre-rejects
    # non-str deps before reaching this function; stringify defensively so
    # this public helper never crashes on a raw dep instead of degrading.
    bad_charset = sorted({str(v) for v in all_values if not id_charset_ok(v)})
    if bad_charset:
        findings.append(f"charset: invalid id(s) (charset/length/segment rule): {bad_charset}")

    return findings


def _find_cycle_members(adjacency: dict[str, list[str]]) -> set[str]:
    """Classic 3-color DFS cycle detection; returns every id on some cycle.

    Edges to an unknown id are skipped here (already reported separately by
    the caller as a "depends on unknown id" structural finding) so a bad
    edge never crashes cycle detection.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(adjacency, WHITE)
    cyclic: set[str] = set()

    def _visit(node: str, stack: list[str]) -> None:
        if color[node] == BLACK:
            return
        if color[node] == GRAY:
            cyclic.update(stack[stack.index(node):])
            return
        color[node] = GRAY
        stack.append(node)
        for dep in adjacency.get(node, []):
            if dep in adjacency:
                _visit(dep, stack)
        stack.pop()
        color[node] = BLACK

    for rid in adjacency:
        if color[rid] == WHITE:
            _visit(rid, [])
    return cyclic


def check_frozen_contracts(rows: list[dict], loop_state_units: list[dict]) -> list[str]:
    """Revert a non-``pending`` unit's ``depends_on`` edit, in place.

    A unit whose ``loop_state.json`` row status is anything other than
    ``pending`` (``in_progress`` / ``merged`` / ``failed``) has already been
    scheduled against its recorded dependency set — its ``depends_on`` can no
    longer change. `rows` (the live campaign.md skeleton) is mutated in
    place: any such unit's ``depends_on`` cell is reverted to the frozen
    ``loop_state.json`` value. Returns one message per unit reverted, naming
    it, so the caller can surface a per-unit warning WITHOUT degrading the
    rest of the campaign's projection (a single bad edit must never brick
    unrelated DAG branches).

    **Case-folded id match** (code review finding, same case-fold-consistency
    class as :func:`validate_dependency_graph`): both the unit-id lookup and
    the frozen-vs-current ``depends_on`` list comparison fold case, so a
    case-mismatched id (e.g. campaign.md's row says ``r0``, ``loop_state.json``
    recorded ``R0``) still finds and freezes the right row instead of
    silently skipping the check.
    """
    frozen_by_id = {
        str(u.get("id")).lower(): (u.get("id"), list(u.get("depends_on") or []))
        for u in loop_state_units
        if u.get("status") not in (None, "pending")
    }
    violations: list[str] = []
    for row in rows:
        rid = row.get("id")
        key = str(rid).lower()
        if key not in frozen_by_id:
            continue
        _frozen_id, frozen = frozen_by_id[key]
        current = list(row.get("depends_on") or [])
        if [str(x).lower() for x in current] != [str(x).lower() for x in frozen]:
            violations.append(
                f"frozen: unit {rid!r} is no longer pending — depends_on edit "
                f"{current} reverted to its frozen value {frozen}"
            )
            row["depends_on"] = frozen
    return violations


def _read_loop_state_units(campaign_dir: Path) -> list[dict]:
    """Best-effort load of ``<project_root>/.shipwright/loop_state.json``'s
    ``units`` list, given a campaign dir anchored under the same
    ``.shipwright`` tree. Missing/corrupt/unanchored -> ``[]`` (no frozen
    contracts recorded yet — never a crash; this is a read-side convenience,
    not the durable source). Schema-invalid but syntactically valid JSON
    (``"units"`` not a list, or containing a non-dict element) also -> ``[]``
    rather than crashing a caller that assumes ``dict``-shaped rows further
    down the pipe (external code review finding, medium). A retained unit
    whose own ``depends_on`` is present but not a list of strings (e.g. a
    hand-edited ``loop_state.json`` with ``"depends_on": 5``) is also dropped:
    :func:`check_frozen_contracts` builds ``list(u.get("depends_on") or [])``,
    and a truthy non-list there raises ``TypeError`` (external Tier-3 PR
    review, blocking)."""
    parts = campaign_dir.resolve().parts
    if ".shipwright" not in parts:
        return []
    project_root = Path(*parts[:parts.index(".shipwright")])
    loop_state_path = project_root / ".shipwright" / "loop_state.json"
    if not loop_state_path.exists():
        return []
    try:
        data = json.loads(loop_state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    units = data.get("units", []) if isinstance(data, dict) else []
    if not isinstance(units, list):
        return []
    return [u for u in units if isinstance(u, dict) and _has_valid_depends_on(u)]


def _has_valid_depends_on(unit: dict) -> bool:
    """A retained unit's ``depends_on``, if present, must be a list of ids."""
    depends_on = unit.get("depends_on")
    return depends_on is None or isinstance(depends_on, list)


def safe_project_campaign_status(campaign_dir: Path | str, events_log: Path | str) -> tuple[dict, dict]:
    """Resume-safe wrapper over :func:`project_campaign_status`.

    Mirrors ``regenerate_campaign_status``'s ``(status, summary)`` return
    exactly, with ``warnings``/``degraded_reason`` living in ``summary``
    where ``campaign_progress.py``'s existing caller already expects them.

    ``check_frozen_contracts`` runs FIRST and reverts a non-pending unit's
    bad edit in place, so a frozen violation degrades only that specific
    unit's ``depends_on`` — the rest of the campaign projects normally —
    even when the reverted edit would ALSO have been structurally invalid on
    its own (external Tier-3 PR review, blocking: running structural
    validation first let exactly that case bypass the per-unit revert and
    degrade the whole projection instead). On a STRUCTURAL
    ``validate_dependency_graph`` violation surviving that revert (duplicate
    / unknown id / self-loop / cycle in a still-``pending`` unit's edit),
    returns the LAST SUCCESSFUL ``status.json`` verbatim plus a ``warnings``
    entry and ``summary["degraded_reason"]`` — never a new top-level
    ``status`` token (that enum is also consumed by an out-of-scope WebUI
    repo). A charset violation only warns (read-time severity is a warning;
    write-time, ``campaign_init.py`` treats it as a hard reject instead).
    """
    campaign_dir = Path(campaign_dir)
    md_path = campaign_dir / "campaign.md"
    status_path = campaign_dir / "status.json"

    committed_status: dict | None = None
    if status_path.exists():
        try:
            committed_status = json.loads(status_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            committed_status = None

    fallback = committed_status or {"sub_iterates": []}
    fallback_campaign = (committed_status or {}).get("campaign", campaign_dir.name)

    if not md_path.exists():
        return fallback, {
            "campaign": fallback_campaign, "warnings": ["campaign.md not found"],
            "degraded_reason": "campaign.md missing",
        }

    md_text = md_path.read_text(encoding="utf-8")

    try:
        rows = parse_campaign_skeleton(md_text)
    except ValueError as exc:
        return fallback, {
            "campaign": fallback_campaign,
            "warnings": [f"skeleton parse error: {exc}"],
            "degraded_reason": f"skeleton parse error: {exc}",
        }

    # External Tier-3 PR review (blocking, campaign-dag-scheduler R1): frozen-
    # contract reversion must happen BEFORE structural validation, not after.
    # An operator edit to a non-pending unit's `depends_on` that ALSO happens
    # to be structurally invalid (e.g. an unknown id) previously hit the
    # structural check first and degraded the WHOLE campaign projection,
    # bypassing the per-unit revert this function's own docstring promises —
    # exactly the "single bad edit must never brick unrelated DAG branches"
    # invariant `check_frozen_contracts` exists to hold. Running the revert
    # first means `validate_dependency_graph` only ever sees the CORRECTED
    # rows, so a frozen unit's bad edit never reaches structural validation
    # at all.
    frozen_findings = check_frozen_contracts(rows, _read_loop_state_units(campaign_dir))

    findings = validate_dependency_graph(rows)
    structural = [f for f in findings if not f.startswith("charset:")]
    charset_findings = [f for f in findings if f.startswith("charset:")]

    if structural:
        return fallback, {
            "campaign": fallback_campaign,
            "warnings": structural + charset_findings + frozen_findings,
            "degraded_reason": f"dependency graph structural violation(s): {'; '.join(structural)}",
        }

    slug = slug_from_md(md_text) or (committed_status or {}).get("campaign") or campaign_dir.name
    events_lines: list[str] = []
    events_log = Path(events_log)
    if events_log.exists():
        events_lines = events_log.read_text(encoding="utf-8").splitlines()

    status, summary = project_campaign_status(md_text, committed_status, events_lines, slug, skeleton=rows)
    summary["warnings"] = list(summary.get("warnings", [])) + charset_findings + frozen_findings
    if frozen_findings:
        summary["degraded_reason"] = f"frozen contract violation(s): {'; '.join(frozen_findings)}"
    return status, summary
