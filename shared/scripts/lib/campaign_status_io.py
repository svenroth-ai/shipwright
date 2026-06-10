"""File-writing + orchestration layer over the pure campaign-status projection.

Campaign ``2026-06-07-tracked-campaign-status`` S3. Keeps ``campaign_status.py``
a (near-)pure projection and centralises the S3 callers — the churn resolver's
full-regen pass and the F5b worktree write — in ONE place, so the host tools
(``resolve_churn_conflicts``, ``finalize_iterate``) stay thin orchestrators at
their bloat ceilings. The serialization is byte-identical to
``campaign_progress._save_status`` and the ``campaign_progress regenerate`` CLI
(single producer): ``json.dumps(indent=2, ensure_ascii=False)``, no trailing
newline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from lib.campaign_status import regenerate_campaign_status
from lib.events_log import resolve_events_path

#: Canonical per-project campaigns directory (whole POSIX path so the
#: artifact-path-canon lint reads `.shipwright/planning` as a unit, not a bare segment).
_CAMPAIGNS_REL = ".shipwright/planning/iterate/campaigns"


def _serialize(status: dict) -> str:
    return json.dumps(status, indent=2, ensure_ascii=False)


def write_campaign_status(campaign_dir, events_log) -> tuple[dict, dict]:
    """Project + persist ``<campaign_dir>/status.json`` (no git staging).

    Returns ``(status, summary)``; propagates ``FileNotFoundError`` (no
    campaign.md / a symlinked target this refuses) / ``ValueError`` (malformed
    skeleton) from the pure producer.
    """
    campaign_dir = Path(campaign_dir)
    status, summary = regenerate_campaign_status(campaign_dir, events_log)
    status_path = campaign_dir / "status.json"
    if status_path.is_symlink():  # never write THROUGH a symlink (parity with finalize guard)
        raise FileNotFoundError(f"refusing symlinked status.json: {status_path}")
    status_path.write_text(_serialize(status), encoding="utf-8")
    return status, summary


def regenerate_campaign_statuses(project_root, events_log, rels) -> dict[str, str]:
    """Re-project ONLY the campaign ``status.json`` files named in ``rels`` (the
    campaigns this merge actually TOUCHED — campaign S3 concurrent-sibling
    regenerate). Returns ``{relpath: "regenerated" | "error"}``; the caller stages.

    Scoped (NOT a glob-all): re-deriving an *untouched* campaign would rewrite it
    from the current projection, which — for a legacy campaign.md the projection
    schema doesn't round-trip exactly — is destructive. The merge only changes the
    board of campaigns whose ``status.json`` conflicted, so the resolver passes
    exactly those. Never-downgrade is intrinsic to the projection.
    """
    project_root = Path(project_root)
    out: dict[str, str] = {}
    for rel in rels:
        camp = project_root / Path(rel).parent          # .../campaigns/<slug>/
        slug = camp.name
        try:
            write_campaign_status(camp, events_log)
            out[rel] = "regenerated"
        except (FileNotFoundError, ValueError) as exc:
            print(f"[campaign_status_io] regen failed for {slug}: {exc}", file=sys.stderr)
            out[rel] = "error"
    return out


def finalize_campaign_status(project_root, event_extras) -> dict:
    """F5b Step-6 entry (S3): when ``event_extras`` carries the S1 campaign stamp
    (``event_extras['campaign']``), re-project that campaign's ``status.json``
    from ``project_root``'s event log and write it into the (worktree) tree so F6
    stages it — demoting the campaign-mode 3g main-tree ``update-status`` to a
    local convenience. Best-effort + no-op for a non-campaign iterate, an absent
    campaign dir/skeleton, a symlink target, or any projection error (the board
    write never blocks finalize). Returns the finalize-step summary dict.
    """
    slug = (event_extras or {}).get("campaign")
    if not slug:
        return {"skipped": True, "reason": "not a campaign sub-iterate"}
    # Validate slug is a single clean path segment: a non-str / traversal / nested
    # slug must NOT join into an arbitrary path (no cross-campaign overwrite) and
    # must NOT crash finalize (a non-str would TypeError in joinpath). Keep ALL
    # filesystem ops below this guard so finalize never blocks on the board write.
    if not isinstance(slug, str) or not slug or "/" in slug or "\\" in slug or slug in (".", ".."):
        return {"skipped": True, "reason": f"invalid campaign slug ({slug!r})"}
    try:
        project_root = Path(project_root)
        campaign_dir = project_root / _CAMPAIGNS_REL / slug
        if not (campaign_dir / "campaign.md").exists():
            return {"skipped": True, "reason": f"campaign.md absent ({slug})"}
        status_path = campaign_dir / "status.json"
        if status_path.is_symlink():
            return {"skipped": True, "reason": "symlink"}
        status, summary = write_campaign_status(
            campaign_dir, resolve_events_path(project_root))  # per-tree log via SSoT resolver
        return {
            "written": str(status_path.relative_to(project_root)),
            "campaign_status": status.get("status"),
            "complete": summary.get("complete"),
            "sub_count": summary.get("sub_count"),
        }
    except Exception as exc:  # noqa: BLE001 best-effort — board write never blocks finalize
        print(f"[campaign_status_io] finalize regen failed: {exc}", file=sys.stderr)
        return {"error": str(exc)}
