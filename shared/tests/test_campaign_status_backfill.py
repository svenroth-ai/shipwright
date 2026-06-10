"""AC1 drift-protection: every tracked campaign's status.json must regenerate
WITHOUT downgrade (campaign 2026-06-07-tracked-campaign-status S4).

Reads the REAL tracked campaigns + event log in this repo (read-only) and runs
the pure projection over each, asserting no committed sub regresses down the
status ladder or vanishes. Guards the S3 lesson: a legacy ``campaign.md`` whose
sub-iterate ids carry markdown emphasis (``**C1**``) must still match the plain
committed ids (``C1``) so a re-projection can't drop a completed sub.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from lib.campaign_status import project_campaign_status

_LADDER = {"pending": 0, "in_progress": 1, "complete": 2}
_REPO_ROOT = Path(__file__).resolve().parents[2]
_CAMPAIGNS = _REPO_ROOT / ".shipwright" / "planning" / "iterate" / "campaigns"


def _campaign_dirs():
    if not _CAMPAIGNS.is_dir():
        return []
    return sorted(p.parent for p in _CAMPAIGNS.glob("*/status.json"))


def _events_lines():
    log = _REPO_ROOT / "shipwright_events.jsonl"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _slug(md_text: str, fallback: str) -> str:
    m = re.search(r"^campaign:\s*(\S+)", md_text, re.MULTILINE)
    return m.group(1) if m else fallback


@pytest.mark.parametrize(
    "campaign_dir", _campaign_dirs(), ids=lambda p: p.name
)
def test_existing_campaign_regenerates_without_downgrade(campaign_dir):
    md = (campaign_dir / "campaign.md").read_text(encoding="utf-8")
    committed = json.loads((campaign_dir / "status.json").read_text(encoding="utf-8"))
    projected, summary = project_campaign_status(
        md, committed, _events_lines(), _slug(md, campaign_dir.name)
    )
    by_id = {s["id"]: s for s in projected["sub_iterates"]}

    for cs in committed.get("sub_iterates", []):
        cid, cstat = cs.get("id"), cs.get("status", "pending")
        ps = by_id.get(cid)
        assert ps is not None, (
            f"{campaign_dir.name}: committed sub {cid!r} ({cstat}) was DROPPED on "
            f"regenerate (skeleton ids: {[s['id'] for s in projected['sub_iterates']]})"
        )
        if cstat in ("failed", "escalated"):
            assert ps["status"] in (cstat, "complete"), (
                f"{campaign_dir.name}: {cid} {cstat} -> {ps['status']} (terminal regressed)"
            )
        else:
            assert _LADDER.get(ps["status"], 0) >= _LADDER.get(cstat, 0), (
                f"{campaign_dir.name}: {cid} downgraded {cstat} -> {ps['status']}"
            )


def test_at_least_one_campaign_present():
    # The repo tracks campaigns; a zero-find means the glob/path broke, which
    # would make the parametrized guard vacuously pass.
    assert _campaign_dirs(), "no tracked campaigns found — backfill guard is vacuous"
