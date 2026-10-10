"""Workflow-enumeration cases split out of ``test_required_checks_drift.py``
(which sat over the size limit): what ``all_workflow_check_names`` does with the
monorepo's own workflows, an empty repo and an unparseable file."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from lib.required_checks_drift import all_workflow_check_names  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]


def test_the_monorepos_manual_launch_gate_is_not_reported_as_drift() -> None:
    """The false positive, pinned against the real file."""
    assert "Empirical calibration (real OSS repos)" not in all_workflow_check_names(_ROOT)


def test_enumeration_survives_a_repo_with_no_workflows(tmp_path: Path) -> None:
    assert all_workflow_check_names(tmp_path) == []


def test_enumeration_skips_an_unparseable_workflow(tmp_path: Path) -> None:
    """One broken file must not take the whole comparison down."""
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "broken.yml").write_text("{{ not: [valid", encoding="utf-8")
    (wf / "ok.yml").write_text(
        "name: X\non:\n  pull_request:\njobs:\n  build:\n    name: Build\n"
        "    runs-on: ubuntu-latest\n    steps:\n      - run: true\n",
        encoding="utf-8",
    )
    assert all_workflow_check_names(tmp_path) == ["Build"]
