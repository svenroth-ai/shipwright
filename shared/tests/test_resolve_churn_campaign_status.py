"""Campaign status.json churn resolution + regenerate-from-events (campaign
2026-06-07-tracked-campaign-status, S3).

A per-campaign ``status.json`` is a tracked per-tree churn artifact at a WILDCARD
path, glob-admitted by ``is_campaign_status`` (not a fixed CHURN_ALLOWLIST entry)
and resolved like a DERIVED_MD: placeholder side at conflict, then re-projected
from the merged event log in the follow-up regenerate. Reuses the git helpers
from ``test_resolve_churn_conflicts`` (same dir, pytest prepend import).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_resolve_churn_conflicts import _git, _make_conflict_repo  # noqa: E402
from tools import resolve_churn_conflicts as rcc  # noqa: E402

_CAMP_REL = ".shipwright/planning/iterate/campaigns/demo/status.json"
_CAMP_MD_REL = ".shipwright/planning/iterate/campaigns/demo/campaign.md"
_CAMPAIGN_MD = """---
campaign: demo
status: active
---

# Campaign: demo

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| S1 | alpha | First | pending |
| S2 | bravo | Second | pending |
"""


def _stamped_event(sid: str, *, slug: str = "demo", ts: str = "2026-06-10T07:00:00+00:00") -> str:
    return json.dumps({
        "type": "work_completed", "ts": ts, "commit": "",
        "campaign": slug, "sub_iterate_id": sid,
        "tests": {"passed": 3, "total": 3},
    })


def test_resolves_campaign_status_conflict_to_placeholder(tmp_path: Path) -> None:
    """A hard campaign status.json conflict is glob-admitted and placeholder-
    resolved to THEIRS (re-projected from events in the follow-up). The pre-flight
    gate must NOT block on it."""
    merge = _make_conflict_repo(
        tmp_path,
        {_CAMP_REL: (
            '{"campaign":"demo","sub_iterates":[]}\n',
            '{"ours":1}\n',
            '{"theirs":2}\n',
        )},
    )
    assert merge.returncode != 0
    result = rcc.complete_merge(tmp_path, run_id=None)
    assert result.status == "resolved"
    assert rcc.conflicted_paths(tmp_path) == []          # now committable
    assert _CAMP_REL in result.resolved
    # placeholder = THEIRS (regenerate re-derives the real projection later).
    assert (tmp_path / _CAMP_REL).read_text(encoding="utf-8") == '{"theirs":2}\n'


def test_campaign_status_md_conflict_blocks_touching_nothing(tmp_path: Path) -> None:
    """campaign.md is curated prose (NOT glob-admitted) — a conflict on it must
    block the whole merge, leaving everything untouched."""
    merge = _make_conflict_repo(
        tmp_path,
        {_CAMP_MD_REL: ("base\n", "ours\n", "theirs\n")},
    )
    assert merge.returncode != 0
    result = rcc.complete_merge(tmp_path, run_id=None)
    assert result.status == "blocked"
    assert _CAMP_MD_REL in result.blocking
    assert result.resolved == []


def _stub_derived(monkeypatch) -> None:
    from tools import finalize_iterate
    monkeypatch.setattr(finalize_iterate, "_update_compliance", lambda pr: [])
    monkeypatch.setattr(finalize_iterate, "_update_dashboard", lambda *a, **k: None)
    monkeypatch.setattr(finalize_iterate, "_generate_handoff", lambda *a, **k: None)
    monkeypatch.setattr(finalize_iterate, "_snapshot_triage_runtime", lambda pr: "skipped")


def _seed_campaign(tmp_path: Path, slug: str = "demo", sid: str = "S1") -> Path:
    campdir = tmp_path / ".shipwright" / "planning" / "iterate" / "campaigns" / slug
    (campdir / "sub-iterates").mkdir(parents=True)
    (campdir / "campaign.md").write_text(_CAMPAIGN_MD.replace("campaign: demo", f"campaign: {slug}"),
                                         encoding="utf-8")
    return campdir


def test_regenerate_reprojects_scoped_campaign_from_events(tmp_path: Path, monkeypatch) -> None:
    """``campaign_status_rels`` scopes the regen: the NAMED campaign is re-projected
    from the merged event log + staged (byte-parity with the pure producer)."""
    _git(tmp_path, "init", "-b", "main")
    campdir = _seed_campaign(tmp_path)
    (tmp_path / "shipwright_events.jsonl").write_text(
        _stamped_event("S1") + "\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "seed campaign + event")

    _stub_derived(monkeypatch)  # isolate the campaign path from heavy MD producers
    outcomes = rcc.regenerate_tracked_snapshots(
        tmp_path, "iterate-x", session_id="s", campaign_status_rels=[_CAMP_REL])

    assert outcomes.get(_CAMP_REL) == "regenerated"
    status = json.loads((tmp_path / _CAMP_REL).read_text(encoding="utf-8"))
    by = {s["id"]: s["status"] for s in status["sub_iterates"]}
    assert by == {"S1": "complete", "S2": "pending"}     # only S1 stamped complete
    # byte-parity with the pure producer (single-producer guarantee).
    from lib.campaign_status import regenerate_campaign_status
    projected, _ = regenerate_campaign_status(campdir, tmp_path / "shipwright_events.jsonl")
    assert (tmp_path / _CAMP_REL).read_text(encoding="utf-8") == json.dumps(
        projected, indent=2, ensure_ascii=False)
    staged = _git(tmp_path, "diff", "--name-only", "--cached").stdout.split()
    assert _CAMP_REL in staged


def test_regenerate_leaves_untouched_campaigns_alone(tmp_path: Path, monkeypatch) -> None:
    """B1 regression: a campaign NOT named in ``campaign_status_rels`` is never
    re-projected — its (possibly legacy / non-round-tripping) board is untouched."""
    _git(tmp_path, "init", "-b", "main")
    _seed_campaign(tmp_path, "demo")
    other = _seed_campaign(tmp_path, "other")
    sentinel = '{"campaign": "other", "LEGACY_FIELD": 1, "sub_iterates": []}'
    (other / "status.json").write_text(sentinel, encoding="utf-8")
    (tmp_path / "shipwright_events.jsonl").write_text(
        _stamped_event("S1", slug="other") + "\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-m", "seed two campaigns")

    _stub_derived(monkeypatch)
    outcomes = rcc.regenerate_tracked_snapshots(
        tmp_path, "iterate-x", session_id="s", campaign_status_rels=[_CAMP_REL])

    # 'other' was NOT named → byte-for-byte untouched (no destructive re-projection).
    assert (other / "status.json").read_text(encoding="utf-8") == sentinel
    assert ".shipwright/planning/iterate/campaigns/other/status.json" not in outcomes


def test_regenerate_skips_campaign_status_without_rels(tmp_path: Path, monkeypatch) -> None:
    """No ``campaign_status_rels`` → NO campaign regen, even on a full derived-MD
    regen (campaign regen is opt-in/scoped, never a glob-all side effect)."""
    _git(tmp_path, "init", "-b", "main")
    campdir = _seed_campaign(tmp_path)
    (tmp_path / "shipwright_events.jsonl").write_text(
        _stamped_event("S1") + "\n", encoding="utf-8")

    _stub_derived(monkeypatch)
    outcomes = rcc.regenerate_tracked_snapshots(tmp_path, "iterate-x", session_id="s")
    assert _CAMP_REL not in outcomes
    assert not (campdir / "status.json").exists()
