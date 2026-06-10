"""Shared builders for the campaign-status projection tests (S2).

Underscore-prefixed so pytest does not collect it as a test module. Imported by
``test_campaign_status.py`` + ``test_campaign_status_project.py`` (both add this
dir to ``sys.path`` first, mirroring the ``_d2v_helpers`` pattern in conftest).
"""

from __future__ import annotations

import json

CAMPAIGN_MD = """---
campaign: demo-campaign
status: active
branch_strategy: stacked
created: 2026-06-07T00:00:00+00:00
expands_triage: trg-deadbeef
---

# Campaign: demo-campaign

## Intent

Do the thing.

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| S1 | alpha | First | pending |
| S2 | bravo | Second | pending |
| S3 | charlie | Third | pending |
"""


def make_committed(**sub_overrides):
    """A committed status.json baseline for demo-campaign (S1..S3)."""
    subs = [
        {"id": "S1", "slug": "alpha", "spec_path": "x/S1-alpha.md",
         "status": "pending", "commit": None, "branch": None,
         "tests_passed": None, "tests_total": None},
        {"id": "S2", "slug": "bravo", "spec_path": "x/S2-bravo.md",
         "status": "pending", "commit": None, "branch": None,
         "tests_passed": None, "tests_total": None},
        {"id": "S3", "slug": "charlie", "spec_path": "x/S3-charlie.md",
         "status": "pending", "commit": None, "branch": None,
         "tests_passed": None, "tests_total": None},
    ]
    for s in subs:
        s.update(sub_overrides.get(s["id"], {}))
    return {
        "campaign": "demo-campaign", "status": "active",
        "branch_strategy": "stacked", "created_at": "2026-06-07T00:00:00+00:00",
        "expands_triage": "trg-deadbeef", "sub_iterates": subs,
    }


def make_event(sid, *, slug="demo-campaign", commit="",
               ts="2026-06-10T07:00:00+00:00", passed=10, total=10,
               type_="work_completed", top_level=True):
    """Serialize one event line. ``top_level=False`` nests the campaign keys
    under ``extras`` (the WRONG shape — must not match, AC4)."""
    ev = {"type": type_, "ts": ts, "commit": commit,
          "tests": {"passed": passed, "total": total}}
    if top_level:
        ev["campaign"] = slug
        ev["sub_iterate_id"] = sid
    else:
        ev["extras"] = {"campaign": slug, "sub_iterate_id": sid}
    return json.dumps(ev)
