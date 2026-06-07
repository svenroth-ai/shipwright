"""Tests for `campaign_init.py --expands-triage / --from-triage`.

Anchoring a campaign to a triage item (stamping `expands_triage` into BOTH
status.json and the campaign.md frontmatter) is what lets the WebUI render the
"Start Campaign" CTA on that triage card. The server join is per-project:
``fm.expandsTriage || fm.expands_triage == item.id`` (shipwright-webui
server/src/core/campaign-store.ts). These tests pin the producer side of that
contract; the snake_case key name is therefore load-bearing.
"""

from __future__ import annotations

import json
import sys
from argparse import Namespace
from pathlib import Path

import pytest

# campaign_init lives in the plugin's scripts/tools; the real triage producer
# (SSoT for the --from-triage round-trip) lives in shared/scripts.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared" / "scripts"))

from campaign_init import init_campaign, main  # noqa: E402
from campaign_progress import _load_status, cmd_start  # noqa: E402


@pytest.fixture
def project(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    return tmp_path


class TestExpandsTriageArtifacts:
    """`expands_triage` lands in BOTH status.json and the frontmatter."""

    VALID_TRG = "trg-abcd1234"

    def test_status_json_carries_expands_triage(self, project):
        result = init_campaign(
            project, "c", "Intent", [{"id": "1.0", "slug": "x"}],
            expands_triage=self.VALID_TRG,
        )
        status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
        assert status["expands_triage"] == self.VALID_TRG

    def test_frontmatter_carries_snake_case_key(self, project):
        # The WebUI reads `fm.expandsTriage || fm.expands_triage`; the snake_case
        # key MUST appear verbatim inside the frontmatter for the join to fire.
        result = init_campaign(
            project, "c", "Intent", [{"id": "1.0", "slug": "x"}],
            expands_triage=self.VALID_TRG,
        )
        md = (Path(result["campaign_dir"]) / "campaign.md").read_text(encoding="utf-8")
        # Value-in-block: the key AND value must live inside the YAML frontmatter,
        # not merely somewhere in the file body.
        frontmatter = md.split("---", 2)[1]
        assert f"expands_triage: {self.VALID_TRG}" in frontmatter

    def test_omitted_when_not_provided(self, project):
        # Backward-compat: an un-anchored campaign carries no `expands_triage`
        # key in either artifact (matches the hand-authored anchor convention).
        result = init_campaign(project, "c", "Intent", [{"id": "1.0", "slug": "x"}])
        status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
        assert "expands_triage" not in status
        md = (Path(result["campaign_dir"]) / "campaign.md").read_text(encoding="utf-8")
        assert "expands_triage" not in md

    def test_result_reports_anchor(self, project):
        result = init_campaign(
            project, "c", "Intent", [{"id": "1.0", "slug": "x"}],
            expands_triage=self.VALID_TRG,
        )
        assert result["expands_triage"] == self.VALID_TRG

    def test_invalid_trg_id_rejected(self, project):
        with pytest.raises(ValueError):
            init_campaign(
                project, "c", "Intent", [{"id": "1.0", "slug": "x"}],
                expands_triage="not-a-trg",
            )

    def test_idempotent_reinit_stable_anchor(self, project):
        # Re-running init with the same anchor overwrites to the same value; the
        # frontmatter holds exactly one anchor line (no accumulation).
        subs = [{"id": "1.0", "slug": "x"}]
        init_campaign(project, "c", "Intent", subs, expands_triage=self.VALID_TRG)
        result = init_campaign(project, "c", "Intent", subs, expands_triage=self.VALID_TRG)
        status = json.loads(Path(result["status_path"]).read_text(encoding="utf-8"))
        assert status["expands_triage"] == self.VALID_TRG
        md = (Path(result["campaign_dir"]) / "campaign.md").read_text(encoding="utf-8")
        assert md.count("expands_triage:") == 1

    def test_anchor_survives_start_roundtrip(self, project):
        # `campaign_progress start` does a load->modify->dump on status.json for
        # the draft->active flip; the anchor MUST survive that round-trip (the
        # boundary probe the touches_io_boundary risk flag enforces). The CTA
        # join still needs the anchor once the campaign goes active ("Go to
        # board").
        result = init_campaign(
            project, "c", "Intent", [{"id": "1.0", "slug": "x"}],
            expands_triage=self.VALID_TRG,
        )
        camp = Path(result["campaign_dir"])
        cmd_start(Namespace(campaign_dir=str(camp)))
        status = _load_status(camp)
        assert status["status"] == "active"
        assert status["expands_triage"] == self.VALID_TRG


class TestExpandsTriageCli:
    """The `main()` CLI boundary: arg validation + both-artifact writes."""

    def _camp(self, project):
        return project / ".shipwright" / "planning" / "iterate" / "campaigns" / "c"

    def test_cli_writes_anchor_to_both(self, project, capsys):
        ret = main([
            "--project-root", str(project),
            "--campaign-slug", "c",
            "--intent", "Big intent",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "x"}]),
            "--expands-triage", "trg-abcd1234",
        ])
        capsys.readouterr()
        assert ret == 0
        camp = self._camp(project)
        status = json.loads((camp / "status.json").read_text(encoding="utf-8"))
        assert status["expands_triage"] == "trg-abcd1234"
        md = (camp / "campaign.md").read_text(encoding="utf-8")
        assert "expands_triage: trg-abcd1234" in md

    def test_cli_invalid_anchor_returns_1(self, project, capsys):
        ret = main([
            "--project-root", str(project),
            "--campaign-slug", "c",
            "--intent", "i",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "x"}]),
            "--expands-triage", "garbage",
        ])
        capsys.readouterr()
        assert ret == 1

    def test_cli_requires_intent_or_from_triage(self, project, capsys):
        ret = main([
            "--project-root", str(project),
            "--campaign-slug", "c",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "x"}]),
        ])
        capsys.readouterr()
        assert ret == 1


class TestFromTriage:
    """`--from-triage` seeds the campaign intent from a real triage item and
    implies the anchor. Uses the real triage producer for a true round-trip.
    """

    def _seed_item(self, project, title, detail):
        import triage  # shared/scripts on sys.path (module top)

        return triage.append_triage_item(
            project,
            source="manual",
            severity="high",
            kind="improvement",
            title=title,
            detail=detail,
        )

    def _camp_md(self, project):
        return (project / ".shipwright" / "planning" / "iterate" / "campaigns" / "c"
                / "campaign.md").read_text(encoding="utf-8")

    def test_from_triage_seeds_intent_and_anchor(self, project):
        trg = self._seed_item(project, "Promote me to a campaign", "Detail body here")
        ret = main([
            "--project-root", str(project),
            "--campaign-slug", "c",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "x"}]),
            "--from-triage", trg,
        ])
        assert ret == 0
        md = self._camp_md(project)
        assert "Promote me to a campaign" in md  # intent seeded from the item
        assert f"expands_triage: {trg}" in md  # --from-triage implies the anchor
        camp = project / ".shipwright" / "planning" / "iterate" / "campaigns" / "c"
        status = json.loads((camp / "status.json").read_text(encoding="utf-8"))
        assert status["expands_triage"] == trg

    def test_explicit_intent_overrides_seed(self, project):
        trg = self._seed_item(project, "Item title", "x")
        ret = main([
            "--project-root", str(project),
            "--campaign-slug", "c",
            "--intent", "Explicit intent wins",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "x"}]),
            "--from-triage", trg,
        ])
        assert ret == 0
        assert "Explicit intent wins" in self._camp_md(project)

    def test_from_triage_unknown_id_returns_1(self, project):
        # Valid shape, absent from the store.
        ret = main([
            "--project-root", str(project),
            "--campaign-slug", "c",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "x"}]),
            "--from-triage", "trg-00000000",
        ])
        assert ret == 1

    def test_from_triage_dismissed_item_warns_but_proceeds(self, project, capsys):
        # Re-promoting a non-open item is allowed but warns: the WebUI hides
        # non-open cards, so the operator should know the CTA may not surface.
        import triage

        trg = self._seed_item(project, "Was dismissed", "d")
        triage.mark_status(project, trg, new_status="dismissed", by="test")
        ret = main([
            "--project-root", str(project),
            "--campaign-slug", "c",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "x"}]),
            "--from-triage", trg,
        ])
        err = capsys.readouterr().err
        assert ret == 0  # not blocked
        assert "WARNING" in err and "dismissed" in err
        # ...and the campaign was still anchored.
        assert f"expands_triage: {trg}" in self._camp_md(project)

    def test_from_triage_conflicting_explicit_anchor_returns_1(self, project):
        trg = self._seed_item(project, "t", "d")
        ret = main([
            "--project-root", str(project),
            "--campaign-slug", "c",
            "--intent", "i",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "x"}]),
            "--from-triage", trg,
            "--expands-triage", "trg-deadbeef",
        ])
        assert ret == 1
