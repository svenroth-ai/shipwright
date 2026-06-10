"""F5b campaign-status wiring (campaign 2026-06-07-tracked-campaign-status, S3).

When the iterate is a campaign sub-iterate, ``finalize_iterate.run`` re-projects
the campaign's ``status.json`` from the event log it just recorded (Step 1) and
writes it into the worktree (Step 6) so F6 stages it — with byte-parity to the
``campaign_progress regenerate`` CLI (single producer). Non-campaign iterates are
a no-op.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.campaign_status import regenerate_campaign_status  # noqa: E402
from tools import finalize_iterate  # noqa: E402

# Valid no-FR classification so the finalize FR-gate (ADR-059) admits the event.
_BASE_EXTRAS = {"change_type": "tooling", "none_reason": "campaign-status wiring test"}

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


@pytest.fixture()
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SHIPWRIGHT_SESSION_ID", raising=False)
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}), encoding="utf-8")
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True)
    (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)
    (tmp_path / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    # keep the run() fast + focused on Step 6 (campaign_status).
    monkeypatch.setattr(finalize_iterate, "_update_compliance", lambda pr: [])
    monkeypatch.setattr(finalize_iterate, "_update_dashboard", lambda *a, **k: None)
    monkeypatch.setattr(finalize_iterate, "_generate_handoff", lambda *a, **k: None)
    monkeypatch.setattr(finalize_iterate, "_snapshot_triage_runtime", lambda pr: "skipped")
    monkeypatch.setattr(finalize_iterate, "_unlink_runtime_artifacts", lambda pr: {})
    return tmp_path


def _make_campaign(project: Path, slug: str = "demo") -> Path:
    cdir = project / ".shipwright" / "planning" / "iterate" / "campaigns" / slug
    (cdir / "sub-iterates").mkdir(parents=True)
    (cdir / "campaign.md").write_text(_CAMPAIGN_MD, encoding="utf-8")
    return cdir


def test_run_regenerates_campaign_status_with_byte_parity(project):
    cdir = _make_campaign(project)
    extras = {**_BASE_EXTRAS, "campaign": "demo", "sub_iterate_id": "S1"}

    result = finalize_iterate.run(project, run_id="iterate-s1", event_extras=extras)

    step = result["steps"]["campaign_status"]
    assert step.get("written", "").endswith("status.json")
    status = json.loads((cdir / "status.json").read_text(encoding="utf-8"))
    by = {s["id"]: s["status"] for s in status["sub_iterates"]}
    assert by == {"S1": "complete", "S2": "pending"}  # Step 1's event projected S1
    # byte-parity with the canonical CLI producer (json.dumps, no trailing newline).
    projected, _ = regenerate_campaign_status(cdir, project / "shipwright_events.jsonl")
    assert (cdir / "status.json").read_text(encoding="utf-8") == json.dumps(
        projected, indent=2, ensure_ascii=False)


def test_run_skips_campaign_status_for_non_campaign_iterate(project):
    cdir = _make_campaign(project)  # campaign exists, but THIS iterate is not in it

    result = finalize_iterate.run(project, run_id="iterate-plain", event_extras=dict(_BASE_EXTRAS))

    step = result["steps"]["campaign_status"]
    assert step.get("skipped") is True
    assert "not a campaign" in step.get("reason", "")
    assert not (cdir / "status.json").exists()  # no board written for a non-campaign run


def test_run_skips_when_campaign_dir_absent(project):
    extras = {**_BASE_EXTRAS, "campaign": "ghost", "sub_iterate_id": "S1"}

    result = finalize_iterate.run(project, run_id="iterate-ghost", event_extras=extras)

    step = result["steps"]["campaign_status"]
    assert step.get("skipped") is True
    assert "absent" in step.get("reason", "")


def test_run_skips_symlinked_status_target(project, tmp_path):
    """A symlinked status.json is refused (never followed). Runs where the OS
    grants symlink creation (POSIX / Win developer-mode); skipped otherwise."""
    cdir = _make_campaign(project)
    real = tmp_path / "real_status.json"
    real.write_text("{}", encoding="utf-8")
    try:
        (cdir / "status.json").symlink_to(real)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted on this host")

    extras = {**_BASE_EXTRAS, "campaign": "demo", "sub_iterate_id": "S1"}
    result = finalize_iterate.run(project, run_id="iterate-sym", event_extras=extras)

    step = result["steps"]["campaign_status"]
    assert step.get("skipped") is True
    assert step.get("reason") == "symlink"
    assert real.read_text(encoding="utf-8") == "{}"  # the symlink target was NOT written through
