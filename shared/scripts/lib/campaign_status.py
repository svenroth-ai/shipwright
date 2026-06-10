"""Pure projection of iterate-campaign status from the event log.

Campaign ``2026-06-07-tracked-campaign-status`` S2 (anchor ``trg-fda5f7a3``).
The WebUI Campaigns board reads each sub-iterate's status from a campaign's
``status.json`` (producer-owned, authoritative per ``campaign-store.ts``). That
file was write-once ``pending`` on a fresh clone, so the board was wrong on a
deployed checkout. S1 made the event log self-identifying (``work_completed``
events now carry **top-level** ``campaign`` / ``sub_iterate_id``); S2 projects
the board from those events so it can be rebuilt from tracked artifacts.

Design (external-review hardened):
- :func:`project_campaign_status` is a **truly-pure core** (no filesystem / no
  git): it takes the ``campaign.md`` text, the committed ``status.json`` dict,
  an iterable of event lines, and the slug — so S3's churn-resolver can feed it
  git-staged blobs directly.
- :func:`regenerate_campaign_status` is the thin file-loading wrapper.
- The skeleton (ids / slugs / titles / **order**) is authoritative: subs in the
  committed status but absent from ``campaign.md`` are dropped (and reported).
- Never-downgrade: a sub's status is the higher rung of
  ``pending < in_progress < complete``; ``failed`` / ``escalated`` are explicit
  and preserved unless a projected ``complete`` (a successful re-run) supersedes.
- ``commit`` / ``tests_*`` carried from the latest matching event only when
  meaningful (a worktree ``commit==""`` never clobbers a committed real sha).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Iterable

#: The monotonic status ladder. ``failed`` / ``escalated`` are deliberately
#: off-ladder (explicit terminal states handled separately in :func:`merge_status`).
STATUS_LADDER: dict[str, int] = {"pending": 0, "in_progress": 1, "complete": 2}
TERMINAL_STATUSES: tuple[str, ...] = ("failed", "escalated")

_FRONTMATTER_CAMPAIGN_RE = re.compile(r"^campaign:\s*(\S+)\s*$", re.MULTILINE)


def all_subs_complete(status: dict) -> bool:
    """True iff the campaign has sub-iterates and every one is complete.

    Canonical SSoT for the lifecycle ``-> complete`` transition (moved here from
    ``campaign_progress.py``; the plugin CLI imports it as ``_all_subs_complete``).
    Takes the *status dict* (not the list) to preserve the original contract.
    """
    subs = status.get("sub_iterates", [])
    return bool(subs) and all(s.get("status") == "complete" for s in subs)


def merge_status(committed: str | None, projected: str | None) -> str:
    """Never-downgrade merge of a committed vs. projected sub-iterate status.

    ``projected`` is only ever ``pending`` or ``complete`` (events can confirm
    completion, never regress). ``failed`` / ``escalated`` in ``committed`` are
    explicit and preserved — unless ``projected`` is ``complete`` (a re-run that
    emitted a fresh ``work_completed`` event supersedes a stale failure).
    Unknown strings rank as 0 (no ``KeyError``).
    """
    committed = committed or "pending"
    projected = projected or "pending"
    if committed in TERMINAL_STATUSES:
        return "complete" if projected == "complete" else committed
    if projected in TERMINAL_STATUSES:  # defensive — projected is pending|complete
        return projected
    return committed if STATUS_LADDER.get(committed, 0) >= STATUS_LADDER.get(projected, 0) else projected


#: Wrapping markdown-emphasis chars stripped from id/slug cells so a legacy
#: ``campaign.md`` (``**C1**``, `` `slug` ``) still matches the plain committed
#: ids — else a re-projection drops the completed sub (S3 downgrade lesson, S4).
_MD_EMPHASIS = "*_`"


def _strip_md(cell: str) -> str:
    """Strip wrapping markdown emphasis (``**bold**``/``*i*``/``_x_``/`` `c` ``)
    and surrounding whitespace. Sub-iterate ids/slugs never contain these chars,
    so this only undoes emphasis a human added to the table."""
    return cell.strip().strip(_MD_EMPHASIS).strip()


def parse_campaign_skeleton(campaign_md_text: str) -> list[dict]:
    """Parse the ``## Sub-Iterates`` markdown table into ``[{id, slug, title}]``.

    Row order is preserved (authoritative for the board). The ``Status`` column
    is intentionally ignored — status comes from projection, not the skeleton.
    Markdown emphasis on the id/slug cells is stripped (``**C1**`` -> ``C1``).
    Raises ``ValueError`` on a missing/empty table, an empty id, or duplicate ids.
    """
    rows: list[dict] = []
    in_section = False
    for line in campaign_md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            in_section = stripped.lower() == "## sub-iterates"
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        # skip the separator row (|---|---|) and the header row (| ID | Slug |...|)
        if all(set(c) <= set("-: ") for c in cells):
            continue
        if cells[0].lower() == "id":
            continue
        rows.append({"id": _strip_md(cells[0]), "slug": _strip_md(cells[1]),
                     "title": cells[2] if len(cells) > 2 else ""})

    if not rows:
        raise ValueError(
            "campaign.md has no '## Sub-Iterates' table rows — cannot project "
            "campaign status (the skeleton drives sub-iterate id/slug/order)."
        )
    ids = [r["id"] for r in rows]
    if any(not i for i in ids):
        raise ValueError("campaign.md skeleton has an empty sub-iterate id.")
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"campaign.md skeleton has duplicate sub-iterate ids: {dupes}")
    return rows


def _ts_sort_key(ev: dict, idx: int) -> tuple[float, int]:
    """Deterministic recency key: parsed ``ts`` epoch, file-index tie-break.

    A missing / unparseable ``ts`` sorts oldest (``-inf``); the file index then
    makes later log lines win, so re-runs without a clean ts still resolve
    last-write-wins rather than nondeterministically.
    """
    ts = ev.get("ts")
    try:
        return (datetime.fromisoformat(ts).timestamp(), idx)
    except (TypeError, ValueError):
        return (float("-inf"), idx)


def _project_events(events_lines: Iterable[str], slug: str) -> tuple[dict[str, dict], list[str]]:
    """Map ``sub_iterate_id -> {commit, tests_passed, tests_total}`` for the
    latest matching ``work_completed`` event, plus a list of warnings.

    Matches on **top-level** ``event["campaign"] == slug`` and a truthy
    ``event["sub_iterate_id"]`` (S1 shape — NOT ``event["extras"]``).
    """
    best: dict[str, tuple] = {}  # sid -> (sort_key, payload)
    corrupt = 0
    for idx, line in enumerate(events_lines):
        if not line.strip():
            continue
        try:
            ev = json.loads(line)
        except (json.JSONDecodeError, TypeError):
            corrupt += 1
            continue
        if not isinstance(ev, dict):  # valid JSON but not an object (e.g. 42, [])
            corrupt += 1
            continue
        if ev.get("type") != "work_completed":
            continue
        if ev.get("campaign") != slug:
            continue
        sid = ev.get("sub_iterate_id")
        if not sid:
            continue
        key = _ts_sort_key(ev, idx)
        if sid in best and key <= best[sid][0]:
            continue
        tests = ev.get("tests") or {}
        best[sid] = (key, {
            "commit": ev.get("commit"),
            "tests_passed": tests.get("passed"),
            "tests_total": tests.get("total"),
        })
    warnings = [f"{corrupt} corrupt/unparseable event line(s) skipped"] if corrupt else []
    return {sid: payload for sid, (_k, payload) in best.items()}, warnings


def project_campaign_status(
    campaign_md_text: str,
    committed_status: dict | None,
    events_lines: Iterable[str],
    slug: str,
) -> tuple[dict, dict]:
    """Project a campaign's ``status.json`` from its skeleton + the event log.

    Pure: no filesystem, no git. Returns ``(status_dict, summary)``. ``summary``
    is a fixed-shape operability record (counts + dropped subs + warnings).
    """
    skeleton = parse_campaign_skeleton(campaign_md_text)
    committed_status = committed_status or {}
    committed_by_id = {s.get("id"): s for s in committed_status.get("sub_iterates", [])}
    projected_by_id, warnings = _project_events(events_lines, slug)

    new_subs: list[dict] = []
    for sk in skeleton:
        sid = sk["id"]
        base = committed_by_id.get(sid, {})
        proj = projected_by_id.get(sid)

        final_status = merge_status(
            base.get("status"), "complete" if proj is not None else "pending"
        )
        commit = base.get("commit")
        if proj and proj.get("commit"):  # non-empty event commit overrides
            commit = proj["commit"]
        tests_passed = base.get("tests_passed")
        if proj and proj.get("tests_passed") is not None:
            tests_passed = proj["tests_passed"]
        tests_total = base.get("tests_total")
        if proj and proj.get("tests_total") is not None:
            tests_total = proj["tests_total"]

        new_subs.append({
            "id": sid,
            "slug": sk["slug"],
            "spec_path": base.get("spec_path"),
            "status": final_status,
            "commit": commit,
            "branch": base.get("branch"),  # events carry no branch
            "tests_passed": tests_passed,
            "tests_total": tests_total,
        })

    skeleton_ids = {sk["id"] for sk in skeleton}
    dropped = sorted(i for i in committed_by_id if i not in skeleton_ids)
    if dropped:
        warnings.append(f"dropped {len(dropped)} sub(s) absent from campaign.md skeleton: {dropped}")

    # Top-level lifecycle: all-subs-complete -> complete regardless of prior
    # (overrides a stale failed/active); otherwise preserve the prior status.
    new_status = {k: v for k, v in committed_status.items() if k != "sub_iterates"}
    new_status["campaign"] = slug
    new_status["sub_iterates"] = new_subs
    if all_subs_complete(new_status):
        new_status["status"] = "complete"

    summary = {
        "campaign": slug,
        "sub_count": len(new_subs),
        "complete": sum(1 for s in new_subs if s["status"] == "complete"),
        "matched_events": len(projected_by_id),
        "dropped_subs": dropped,
        "warnings": warnings,
    }
    return new_status, summary


def _slug_from_md(campaign_md_text: str) -> str | None:
    m = _FRONTMATTER_CAMPAIGN_RE.search(campaign_md_text)
    return m.group(1) if m else None


def regenerate_campaign_status(campaign_dir, events_log) -> tuple[dict, dict]:
    """File-loading wrapper over :func:`project_campaign_status`.

    Reads ``<campaign_dir>/campaign.md`` (raises ``FileNotFoundError`` if absent),
    the committed ``<campaign_dir>/status.json`` baseline (if present), and the
    ``events_log`` lines (missing log = no projection). Fills a derived
    ``spec_path`` for any skeleton sub the committed status didn't carry. Performs
    no write / no git — the caller (CLI / S3 finalize) persists the dict.
    """
    campaign_dir = Path(campaign_dir)
    md_path = campaign_dir / "campaign.md"
    if not md_path.exists():
        raise FileNotFoundError(f"campaign.md not found in {campaign_dir}")
    md_text = md_path.read_text(encoding="utf-8")

    status_path = campaign_dir / "status.json"
    committed = None
    committed_warning = None
    if status_path.exists():
        try:
            committed = json.loads(status_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            # The committed status.json is exactly what we are rebuilding, so a
            # corrupt/half-written one must NOT crash regenerate — rebuild from
            # campaign.md + events with no baseline (and report it). This keeps
            # "rebuild the board from tracked artifacts" true even after a bad write.
            committed_warning = "committed status.json was corrupt — rebuilt with no baseline"

    slug = _slug_from_md(md_text) or (committed or {}).get("campaign") or campaign_dir.name

    events_lines: list[str] = []
    events_log = Path(events_log)
    if events_log.exists():
        events_lines = events_log.read_text(encoding="utf-8").splitlines()

    status, summary = project_campaign_status(md_text, committed, events_lines, slug)
    if committed_warning:
        summary["warnings"].append(committed_warning)

    for sub in status["sub_iterates"]:
        if not sub.get("spec_path"):
            sub["spec_path"] = str(campaign_dir / "sub-iterates" / f"{sub['id']}-{sub['slug']}.md")
    return status, summary
