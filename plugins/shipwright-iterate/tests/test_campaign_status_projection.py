"""Plugin-side tests for the campaign-status regenerate CLI + cross-layer wiring.

Covers (campaign S2, anchor trg-fda5f7a3):
- the ``campaign_progress.py regenerate`` thin CLI wrapper,
- the producer<->parser contract (real ``campaign_init`` output parses),
- the ``all_subs_complete`` import-alias identity (single SSoT),
- a hermetic boundary probe over the real S1 ``work_completed`` event shape
  (top-level ``campaign``/``sub_iterate_id``, ``commit=''``).
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "scripts" / "tools"
sys.path.insert(0, str(_TOOLS))
# shared lib (parse_campaign_skeleton) — same walk-up campaign_progress uses
for _p in _TOOLS.parents:
    _cand = _p / "shared" / "scripts"
    if _cand.is_dir():
        sys.path.insert(0, str(_cand))
        break

from campaign_init import init_campaign  # noqa: E402
from campaign_progress import _load_status  # noqa: E402
from lib.campaign_status import parse_campaign_skeleton  # noqa: E402


def _project(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8")
    return tmp_path


def _make_campaign(tmp_path):
    subs = [
        {"id": "S1", "slug": "alpha", "title": "First", "scope": "a"},
        {"id": "S2", "slug": "bravo", "title": "Second", "scope": "b"},
    ]
    result = init_campaign(_project(tmp_path), "demo", "Intent", subs, "stacked")
    return Path(result["campaign_dir"])


def _s1_event(sid, slug, *, commit="", passed=3457, total=3458):
    """An event mirroring the real merged S1 shape (top-level keys, commit='')."""
    return json.dumps({
        "intent": "feature", "type": "work_completed", "source": "iterate",
        "commit": commit, "ts": "2026-06-10T07:31:00.326550+00:00",
        "tests": {"passed": passed, "total": total, "e2e_run": True},
        "campaign": slug, "sub_iterate_id": sid,
        "id": "evt-c064117a", "v": 1,
    })


class TestProducerParserContract:
    """campaign_init writes the table; parse_campaign_skeleton reads it. Drift
    in either side must break this test (Registry-driven SSoT, both directions)."""

    def test_real_campaign_md_parses(self, tmp_path):
        cdir = _make_campaign(tmp_path)
        md = (cdir / "campaign.md").read_text(encoding="utf-8")
        skeleton = parse_campaign_skeleton(md)
        assert [s["id"] for s in skeleton] == ["S1", "S2"]
        assert [s["slug"] for s in skeleton] == ["alpha", "bravo"]
        assert skeleton[0]["title"] == "First"


class TestAllSubsCompleteAlias:
    def test_alias_is_the_shared_canonical(self):
        import campaign_progress
        from lib.campaign_status import all_subs_complete
        # one definition: the plugin alias IS the shared function object.
        assert campaign_progress._all_subs_complete is all_subs_complete


class TestRegenerateCli:
    def _run(self, cdir, events_log):
        from campaign_progress import cmd_regenerate
        return cmd_regenerate(Namespace(campaign_dir=str(cdir), events_log=str(events_log)))

    def test_writes_status_and_prints_summary(self, tmp_path, capsys):
        cdir = _make_campaign(tmp_path)
        ev = tmp_path / "shipwright_events.jsonl"
        ev.write_text("\n".join([_s1_event("S1", "demo"), _s1_event("S2", "demo")]),
                      encoding="utf-8")
        assert self._run(cdir, ev) == 0
        summary = json.loads(capsys.readouterr().out)
        assert summary["campaign"] == "demo"
        assert summary["matched_events"] == 2
        assert summary["output_path"].endswith("status.json")
        status = _load_status(cdir)
        assert [s["status"] for s in status["sub_iterates"]] == ["complete", "complete"]
        assert status["status"] == "complete"

    def test_missing_md_returns_1(self, tmp_path, capsys):
        empty = tmp_path / "empty"
        empty.mkdir()
        ev = tmp_path / "shipwright_events.jsonl"
        ev.write_text("", encoding="utf-8")
        assert self._run(empty, ev) == 1
        # clean error surface + no status.json written on the failure path
        assert "ERROR" in capsys.readouterr().err
        assert not (empty / "status.json").exists()

    def test_boundary_probe_real_s1_shape_no_clobber(self, tmp_path, capsys):
        """The real S1 event has commit='' (worktree flow). A committed real
        commit must survive regeneration; status stays complete."""
        cdir = _make_campaign(tmp_path)
        # committed baseline: S1 already complete with a real sha (no event yet)
        status = _load_status(cdir)
        status["sub_iterates"][0].update(
            {"status": "complete", "commit": "efa1dcfc3a5ea0b2ae89bac3a367109511093591"})
        (cdir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")
        ev = tmp_path / "shipwright_events.jsonl"
        ev.write_text(_s1_event("S1", "demo", commit=""), encoding="utf-8")
        assert self._run(cdir, ev) == 0
        after = _load_status(cdir)
        s1 = after["sub_iterates"][0]
        assert s1["status"] == "complete"
        assert s1["commit"] == "efa1dcfc3a5ea0b2ae89bac3a367109511093591"
        assert s1["tests_passed"] == 3457  # event tests carried
