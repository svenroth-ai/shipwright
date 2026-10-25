"""Project brief mode: the grill gates satisfied by CONTENT (campaign brief-driven-run, B2; BRIEF D3)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))

from _brief_dir_helpers import CAPTURE, DEFAULT_MD, GLOSSARY, LIST_NOTES, build_package, write_config  # noqa: E402
import tools.brief_project_mode as bpm  # noqa: E402
from tools.grill_trace_format import read_trace_dir  # noqa: E402
bdi = bpm.bdi  # the module the tool itself uses (same exception class)

GATE = Path(bpm.__file__).resolve().parent / "verify_grill_trace_completeness.py"
TOOL = Path(bpm.__file__).resolve()


def _project(tmp_path, md=DEFAULT_MD, **kw):
    build_package(tmp_path, md, **kw)
    write_config(tmp_path)
    bdi.record(tmp_path, "brief")
    return tmp_path


def _gate(root: Path):
    return subprocess.run([sys.executable, str(GATE), "--project-root", str(root)], capture_output=True, text=True)


@pytest.mark.covers("FR-01.02")
def test_apply_writes_artifacts_that_pass_the_real_grill_gate(tmp_path):
    root = _project(tmp_path)
    out = bpm.apply(root)
    assert out["ok"] and out["capabilities"] == ["capture-note", "list-notes"]
    planning = root / ".shipwright" / "planning"
    assert "no interview was held" in (planning / "shipwright_project_interview.md").read_text(encoding="utf-8")
    assert "## Capture note" in (planning / "requirements.md").read_text(encoding="utf-8")
    traces = {t.requirement_key: t for t in read_trace_dir(planning)}
    assert traces["capture-note"].evidence == ("brief.md#capture-note",)
    assert traces["capture-note"].confirmed_by == "brief:brief/brief.md"
    assert traces["list-notes"].terms_used == ("Notes",)  # glossary term used by that section
    assert "**Notes**" in (root / "CONTEXT.md").read_text(encoding="utf-8")
    gate = _gate(root)
    assert gate.returncode == 0, gate.stdout + gate.stderr


@pytest.mark.covers("FR-01.02")
def test_apply_is_idempotent(tmp_path):
    root = _project(tmp_path)
    bpm.apply(root)
    first = (root / "CONTEXT.md").read_bytes()
    assert bpm.apply(root)["ok"]
    assert (root / "CONTEXT.md").read_bytes() == first


@pytest.mark.covers("FR-01.02")
def test_an_empty_section_is_refused_and_nothing_is_written(tmp_path):
    root = _project(tmp_path, DEFAULT_MD + "\n## Ghost\n\n")
    out = bpm.apply(root)
    assert not out["ok"] and out["issues"][0]["code"] == "empty_section"
    assert not (root / ".shipwright").exists() and not (root / "CONTEXT.md").exists()


@pytest.mark.covers("FR-01.02")
def test_each_dimension_text_must_be_non_empty_and_assumed_is_refused():
    for needle, repl, code in (
        ("- Purpose: keep ideas from getting lost\n", "- Purpose:\n", "empty_dimension"),
        ("- Failure: an empty title is refused with a message\n", "- Failure: assumed: fine\n", "assumed_not_allowed"),
        ("- Rationale: n/a: the simplest capture flow\n", "- Rationale: n/a:\n", "empty_dimension"),
        ("- Fit criterion: a note added with a title is listed within one second\n", "", "no_fit_criterion"),
    ):
        issues = bpm.check_capabilities(*bpm.parse_brief_md(DEFAULT_MD.replace(needle, repl)))
        assert [i["code"] for i in issues] == [code], (code, issues)


@pytest.mark.covers("FR-01.02")
def test_prose_only_sections_do_not_pass_the_content_check(tmp_path):
    md = "# Notes\n\n## capture-note\nA user can add a note.\n"
    issues = bpm.check_capabilities(*bpm.parse_brief_md(md))
    assert {i["code"] for i in issues} == {"empty_dimension"}


@pytest.mark.covers("FR-01.02")
def test_apply_needs_a_verified_package(tmp_path):
    root = _project(tmp_path)
    (root / "brief" / "scope.md").write_text("tampered\n", encoding="utf-8")
    try:
        bpm.apply(root)
    except bdi.BriefRefused as exc:
        assert exc.code == "hash_mismatch"
    else:
        raise AssertionError("a tampered package must be refused")
    assert not (root / ".shipwright").exists()
    cli = subprocess.run([sys.executable, str(TOOL), "apply", "--project-root", str(root)], capture_output=True, text=True)
    assert cli.returncode == 3


@pytest.mark.covers("FR-01.02")
def test_an_anchor_that_resolves_to_an_empty_section_fails_verify_traces(tmp_path):
    root = _project(tmp_path, DEFAULT_MD + "\n## Ghost\n")
    planning = root / ".shipwright" / "planning"
    assert bpm.apply(root)["ok"] is False  # content refused ...
    trace = bpm.build_trace(bpm.parse_brief_md(CAPTURE + LIST_NOTES)[0][0], {}, "brief/brief.md")
    trace.update(requirement_key="ghost", evidence=["brief.md#ghost"])
    from tools.write_grill_trace import write_trace
    write_trace(planning, trace, lock_timeout=5.0)  # ... but a hand-written trace still points at the void
    out = bpm.verify_traces(root)
    assert not out["ok"] and out["issues"][0]["code"] == "anchor_empty"
    trace.update(requirement_key="loose", evidence=["turn 3: said so"])
    write_trace(planning, trace, lock_timeout=5.0)
    assert "evidence_not_anchored" in {i["code"] for i in bpm.verify_traces(root)["issues"]}


@pytest.mark.covers("FR-01.02")
def test_valid_anchors_pass_verify_traces(tmp_path):
    root = _project(tmp_path)
    bpm.apply(root)
    assert bpm.verify_traces(root) == {"ok": True, "issues": []}


def _spec(root: Path, names: list[str]) -> None:
    rows = "".join(f"| FR-01.{i:02d} | Notes | {n} | Must | text | b | l |\n" for i, n in enumerate(names, 1))
    d = root / ".shipwright" / "planning" / "01-notes"
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text("## Functional Requirements\n\n| ID | Area | Name | Priority | Description | Basis | Layers |\n"
                               "|---|---|---|---|---|---|---|\n" + rows, encoding="utf-8")


@pytest.mark.covers("FR-01.02")
def test_fr_names_must_equal_the_brief_names(tmp_path):
    root = _project(tmp_path)
    _spec(root, ["Capture note", "List notes"])
    assert bpm.check_fr_names(root)["ok"] is True
    _spec(root, ["Capture note", "List all notes"])
    out = bpm.check_fr_names(root)
    assert out == {"ok": False, "missing_in_specs": ["List notes"], "not_in_brief": ["List all notes"]}


@pytest.mark.covers("FR-01.02")
def test_glossary_section_is_not_a_capability():
    caps, glossary = bpm.parse_brief_md(DEFAULT_MD)
    assert [c["name"] for c in caps] == ["Capture note", "List notes"]
    assert list(glossary) == ["Notes"] and GLOSSARY.strip()


@pytest.mark.covers("FR-01.02")
def test_the_real_project_gate_fails_on_an_anchor_that_resolves_to_an_empty_section(tmp_path):
    from tools.verifiers.brief_mode_checks import check_brief_evidence_anchors, check_brief_fr_names
    from tools.verifiers.project_checks import run_project_checks
    from tools.write_grill_trace import write_trace

    root = _project(tmp_path, DEFAULT_MD + "\n## Ghost\n")
    planning = root / ".shipwright" / "planning"
    trace = bpm.build_trace(bpm.parse_brief_md(CAPTURE + LIST_NOTES)[0][0], {}, "brief/brief.md")
    trace.update(requirement_key="ghost", evidence=["brief.md#ghost"])
    write_trace(planning, trace, lock_timeout=5.0)
    [res] = check_brief_evidence_anchors(root)
    assert res.ok is False and "anchor_empty" in res.detail
    names = [r.name for r in run_project_checks(root)]
    assert "brief_evidence_anchors" in names and "brief_fr_names" in names
    assert check_brief_fr_names(root)[0].severity == "skipped"  # no spec.md yet


@pytest.mark.covers("FR-01.02")
def test_the_real_project_gate_checks_fr_names_and_ignores_runs_without_a_brief(tmp_path):
    from tools.verifiers.brief_mode_checks import check_brief_evidence_anchors, check_brief_fr_names

    root = _project(tmp_path)
    bpm.apply(root)
    assert check_brief_evidence_anchors(root)[0].ok is True
    _spec(root, ["Capture note", "List notes"])
    assert check_brief_fr_names(root)[0].ok is True
    _spec(root, ["Capture note"])
    assert check_brief_fr_names(root)[0].ok is False
    plain = tmp_path / "plain"
    plain.mkdir()
    assert check_brief_evidence_anchors(plain) == [] and check_brief_fr_names(plain) == []


@pytest.mark.covers("FR-01.02")
def test_a_brief_run_rejects_traces_that_are_not_anchored_to_their_own_section(tmp_path):
    from tools.verifiers.brief_mode_checks import check_brief_evidence_anchors
    from tools.write_grill_trace import write_trace

    root = _project(tmp_path)
    bpm.apply(root)
    planning = root / ".shipwright" / "planning"
    base = bpm.build_trace(bpm.parse_brief_md(CAPTURE)[0][0], {}, "brief/brief.md")
    write_trace(planning, {**base, "requirement_key": "other", "evidence": ["brief.md#capture-note"]}, lock_timeout=5.0)
    assert "anchor_key_mismatch" in check_brief_evidence_anchors(root)[0].detail
    write_trace(planning, {**base, "requirement_key": "other", "evidence": ["brief.md#other"],
                           "confirmed_by": "user said so"}, lock_timeout=5.0)
    assert "wrong_source" in check_brief_evidence_anchors(root)[0].detail


@pytest.mark.covers("FR-01.02")
def test_a_duplicate_label_is_reported():
    issues = bpm.check_capabilities(*bpm.parse_brief_md(DEFAULT_MD.replace("- Purpose:", "- Outcome: again\n- Purpose:", 1)))
    assert "duplicate_label" in {i["code"] for i in issues}


@pytest.mark.covers("FR-01.02")
def test_fr_names_check_is_red_when_specs_exist_but_no_fr_row_parses(tmp_path):
    from tools.verifiers.brief_mode_checks import check_brief_fr_names

    root = _project(tmp_path)
    d = root / ".shipwright" / "planning" / "01-notes"
    d.mkdir(parents=True)
    (d / "spec.md").write_text("## Functional Requirements\n\nnothing parseable here\n", encoding="utf-8")
    assert check_brief_fr_names(root)[0].ok is False


@pytest.mark.covers("FR-01.02")
def test_a_capability_without_any_trace_is_red(tmp_path):
    from tools.verifiers.brief_mode_checks import check_brief_evidence_anchors
    from tools.write_grill_trace import write_trace

    root = _project(tmp_path)
    base = bpm.build_trace(bpm.parse_brief_md(CAPTURE)[0][0], {}, "brief/brief.md")
    write_trace(root / ".shipwright" / "planning", base, lock_timeout=5.0)
    res = check_brief_evidence_anchors(root)[0]
    assert res.ok is False and "missing_trace" in res.detail


@pytest.mark.covers("FR-01.02")
def test_glossary_accepts_both_bold_colon_forms_and_reports_unparsed_lines():
    md = DEFAULT_MD.replace(GLOSSARY, "## Glossary\n- **Notes:** the saved texts.\n- **Tag**: a label.\nloose prose line\n")
    _caps, glossary = bpm.parse_brief_md(md)
    assert glossary == {"Notes": "the saved texts.", "Tag": "a label."}
    assert bpm.glossary_unparsed(md) == ["loose prose line"]


@pytest.mark.covers("FR-01.02")
def test_headings_inside_fenced_code_are_not_sections_and_closing_hashes_follow_commonmark():
    md = DEFAULT_MD + "\n```\n## Not a section\n```\n\n## Report C# ##\nRequirement: x\n"
    names = [c["name"] for c in bpm.parse_brief_md(md)[0]]
    assert "Not a section" not in names and "Report C#" in names


@pytest.mark.covers("FR-01.02")
def test_apply_refuses_an_unparsed_glossary_line_before_any_write(tmp_path):
    root = _project(tmp_path, DEFAULT_MD.replace(GLOSSARY, GLOSSARY + "stray line\n"))
    out = bpm.apply(root)
    assert out["ok"] is False and out["issues"][0]["code"] == "glossary_line_unparsed"
    assert not (root / ".shipwright" / "planning" / "requirements.md").exists()
