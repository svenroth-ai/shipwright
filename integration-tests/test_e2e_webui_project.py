"""B7 acceptance that needs no model: the social engagement board package validates and passes A1's dry harness,
and the operator-started WebUI spec project keeps its structural promises (no defaults for the operator
inputs, 300-line cap per .ts file, fixed-argv child processes, nothing secret or user-specific committed).
The real run is operator acceptance; its type check is the local `npm run typecheck`."""

import json
import re
import sys
from pathlib import Path

import pytest

import _brief_harness as h

_REPO = Path(__file__).resolve().parents[1]
FIXTURE = _REPO / "integration-tests" / "fixtures" / "social-engagement-board"
EXPECTED = _REPO / "integration-tests" / "fixtures" / "social-engagement-board-expected-result.md"
PROJECT = _REPO / "integration-tests" / "e2e-webui"
TS_FILES = sorted(p for p in PROJECT.rglob("*.ts") if "node_modules" not in p.parts)


def _brief_package():
    sys.path.insert(0, str(_REPO / "shared" / "scripts"))
    try:
        from lib import brief_package  # noqa: PLC0415
    finally:
        sys.path.remove(str(_REPO / "shared" / "scripts"))
    return brief_package


@pytest.mark.covers("FR-01.06")
def test_package_validates_and_hash_matches_the_recorded_one():
    bp = _brief_package()
    recorded = json.loads((FIXTURE / "brief.json").read_text(encoding="utf-8"))["package_sha256"]
    ok, issues = bp.verify_package(FIXTURE, expected=recorded)
    assert ok, issues
    assert not (FIXTURE / "expected-result.md").exists(), "the answer key must stay outside the hashed package"


@pytest.mark.covers("FR-01.06")
def test_package_brief_md_passes_the_project_phase_content_check():
    """The first real run stopped in the project phase: 42 empty dimensions, one unparsed glossary line."""
    sys.path.insert(0, str(_REPO / "shared" / "scripts"))
    try:
        from tools import brief_project_mode as bpm  # noqa: PLC0415
    finally:
        sys.path.remove(str(_REPO / "shared" / "scripts"))
    text = (FIXTURE / "brief.md").read_text(encoding="utf-8")
    assert bpm.check_capabilities(*bpm.parse_brief_md(text)) == []
    assert bpm.glossary_unparsed(text) == []


@pytest.mark.covers("FR-01.06")
def test_package_passes_the_dry_harness(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_ACCEPT_FIXTURE_APPROVAL", "1")
    project = h.prepare_scratch_project(tmp_path / "proj", FIXTURE)
    report = h.run_harness(project, fixture="social-engagement-board", report_path=tmp_path / "report.json")
    assert report["outcome"] == "dry-ok", report


@pytest.mark.covers("FR-01.06")
def test_checklist_has_hard_and_soft_items_with_unique_ids():
    items = re.findall(r"^- \[(hard|soft)\] ([A-Z]\d+): .+$", EXPECTED.read_text(encoding="utf-8"), re.M)
    assert {kind for kind, _ in items} == {"hard", "soft"}
    ids = [i for _, i in items]
    assert len(ids) == len(set(ids))


@pytest.mark.covers("FR-01.06")
def test_every_typescript_file_stays_within_the_bloat_cap():
    assert TS_FILES, "the spec project has no .ts files"
    over = {str(p.relative_to(PROJECT)): n for p in TS_FILES if (n := len(p.read_text(encoding="utf-8").splitlines())) > 300}
    assert over == {}


@pytest.mark.covers("FR-01.06")
def test_gitignore_and_env_example_keep_secrets_and_output_out():
    ignore = (PROJECT / ".gitignore").read_text(encoding="utf-8").split()
    assert "node_modules/" in ignore and "e2e-report/" in ignore
    example = (PROJECT / ".env.example").read_text(encoding="utf-8")
    for line in example.splitlines():
        if line and not line.startswith("#"):
            name, _, value = line.partition("=")
            assert re.fullmatch(r"SHIPWRIGHT_E2E_[A-Z_]+", name) and value == "", line


@pytest.mark.covers("FR-01.06")
def test_operator_inputs_have_no_defaults_and_children_use_fixed_argv():
    env_ts = (PROJECT / "src" / "env.ts").read_text(encoding="utf-8")
    assert not re.search(r"SHIPWRIGHT_E2E_(PERMISSION_MODE|WEBUI_DIR|MAX_MINUTES)\s*(\?\?|\|\|)", env_ts)
    for path in TS_FILES:
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"shell\s*:\s*true|(?<![.\w])(?:exec|execSync)\(", text), path
        assert not re.search(r"[A-Za-z]:\\\\Users|/Users/|/home/\w", text), f"hard-coded user path in {path}"


@pytest.mark.covers("FR-01.06")
def test_template_placeholders_are_all_known_to_the_report_writer():
    template = (PROJECT / "report-template.md").read_text(encoding="utf-8")
    writer = (PROJECT / "src" / "report.ts").read_text(encoding="utf-8")
    for key in set(re.findall(r"\{\{([A-Z_]+)\}\}", template)):
        assert f"{key}:" in writer, key
