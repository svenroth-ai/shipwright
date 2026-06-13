"""`serial` is the interleaved-campaign default for campaign_init.

Separate file (not test_campaign.py) to keep that file under the 300-LOC
guideline. Serial = build one sub-iterate -> PR -> CI-green -> merge -> build the
next from fresh origin/main; it is the only documented campaign model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "tools"))

from campaign_init import init_campaign, main


@pytest.fixture
def project(tmp_path):
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    return tmp_path


def _status(project: Path, slug: str) -> dict:
    p = project / ".shipwright" / "planning" / "iterate" / "campaigns" / slug / "status.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_init_campaign_default_is_serial(project):
    """init_campaign with no explicit strategy now defaults to serial."""
    result = init_campaign(project, "camp", "Intent", [{"id": "1.0", "slug": "a"}])
    assert result["branch_strategy"] == "serial"
    assert _status(project, "camp")["branch_strategy"] == "serial"


def test_cli_default_is_serial(project):
    """Omitting --branch-strategy on the CLI writes serial."""
    rc = main([
        "--project-root", str(project),
        "--campaign-slug", "cli-default",
        "--intent", "x",
        "--sub-iterates", json.dumps([{"id": "1.0", "slug": "a"}]),
    ])
    assert rc == 0
    assert _status(project, "cli-default")["branch_strategy"] == "serial"


def test_cli_accepts_serial_explicitly(project):
    rc = main([
        "--project-root", str(project),
        "--campaign-slug", "cli-serial",
        "--intent", "x",
        "--sub-iterates", json.dumps([{"id": "1.0", "slug": "a"}]),
        "--branch-strategy", "serial",
    ])
    assert rc == 0
    assert _status(project, "cli-serial")["branch_strategy"] == "serial"


def test_cli_still_accepts_stacked(project):
    """Legacy stacked stays a valid CLI choice (back-compat for old campaigns)."""
    rc = main([
        "--project-root", str(project),
        "--campaign-slug", "cli-stacked",
        "--intent", "x",
        "--sub-iterates", json.dumps([{"id": "1.0", "slug": "a"}]),
        "--branch-strategy", "stacked",
    ])
    assert rc == 0
    assert _status(project, "cli-stacked")["branch_strategy"] == "stacked"


def test_cli_rejects_unknown_strategy(project):
    """argparse `choices` reject a bogus strategy (SystemExit from argparse)."""
    with pytest.raises(SystemExit):
        main([
            "--project-root", str(project),
            "--campaign-slug", "bogus",
            "--intent", "x",
            "--sub-iterates", json.dumps([{"id": "1.0", "slug": "a"}]),
            "--branch-strategy", "parallel",
        ])
