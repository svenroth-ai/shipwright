"""Cross-component: the resolver CLI's output composes with the review-record CLI.

``campaign-mode.md`` threads ONE resolved literal (from ``resolve_model_tier.py``)
into both the Agent-tool spawn AND the matching ``record_review_pass.py
--model-tier`` call, for the whole campaign run, without either side re-reading
``shipwright_model_config.json`` itself (`cross_component`, since this diff
touches ``campaign-mode.md``'s own trigger pattern). A unit test on each CLI in
isolation cannot prove that composition holds — this drives them together,
project-config resolution through to the recorded reviews.json entry, over a
real subprocess boundary on both sides.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))

from lib.review_record import record_path  # noqa: E402

_RESOLVER = str(_SHARED / "scripts" / "tools" / "resolve_model_tier.py")


def _resolve(project: Path, *extra_args: str) -> dict:
    proc = subprocess.run(
        [sys.executable, _RESOLVER, "--project-root", str(project), *extra_args],
        capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def test_project_config_resolved_tier_composes_into_the_review_record(tmp_path: Path) -> None:
    """The literal `resolve_model_tier.py` prints for `review` is exactly what
    lands in reviews.json when threaded through `--model-tier`, unmodified."""
    project = make_project(tmp_path)
    (project / "shipwright_model_config.json").write_text(
        json.dumps({"review": "opus"}), encoding="utf-8")

    resolved = _resolve(project)
    assert resolved["review"] == {"resolved": "opus", "source": "project_config", "agent_param": "opus"}

    rc, out = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--recorded-by", "code-reviewer", "--model-tier", resolved["review"]["resolved"],
    )
    assert rc == 0, out
    entry = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))["reviews"]["code"]
    assert entry["model_tier"] == "opus"


def test_flag_overrides_project_config_end_to_end(tmp_path: Path) -> None:
    """flag > project config holds across the two-process boundary, not just
    inside the resolver's own unit tests."""
    project = make_project(tmp_path)
    (project / "shipwright_model_config.json").write_text(
        json.dumps({"review": "opus"}), encoding="utf-8")

    resolved = _resolve(project, "--review-model", "sonnet")
    assert resolved["review"] == {"resolved": "sonnet", "source": "flag", "agent_param": "sonnet"}

    rc, out = run_tool(
        project, "record", "--review-type", "spec", "--status", "completed",
        "--recorded-by", "spec-reviewer", "--model-tier", resolved["review"]["resolved"],
    )
    assert rc == 0, out
    entry = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))["reviews"]["spec"]
    assert entry["model_tier"] == "sonnet"


def test_unset_role_resolves_to_inherit_and_is_never_recorded(tmp_path: Path) -> None:
    """A role campaign-mode.md never resolved a flag/config for stays `inherit`;
    the SKILL.md instruction is to omit `--model-tier` for that role, and the
    entry must carry no key at all — not a stray `"model_tier": "inherit"`."""
    project = make_project(tmp_path)

    resolved = _resolve(project)
    assert resolved["finalization"] == {"resolved": "inherit", "source": "unset", "agent_param": None}

    rc, out = run_tool(
        project, "record", "--review-type", "doubt", "--status", "completed",
        "--recorded-by", "doubt-reviewer",
    )
    assert rc == 0, out
    entry = json.loads(record_path(project, RUN_ID).read_text(encoding="utf-8"))["reviews"]["doubt"]
    assert "model_tier" not in entry
