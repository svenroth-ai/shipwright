"""atomic-frs U1: the spec-time scope gate of /shipwright-project. Two stand-in brief outputs pass; broken FRs are named."""

from __future__ import annotations

import pytest

from lib.fr_scope_check import check_spec
from tools import fr_scope_check as cli

# Specs shaped like the skill's output for two small briefs (leave requests; recipe box), one capability per FR.
BRIEF_LEAVE = """## Functional Requirements

| ID | Area | Name | Priority | Description | Basis | Layers |
|----|------|------|----------|-------------|-------|--------|
| FR-01.01 | Requests | Request time off | Must | The system SHALL let an employee request time off. | interview | unit |
| FR-01.02 | Requests | Approve a request | Must | The system SHALL let a manager approve a request. | interview | unit |

### FR-01.01 - Request time off

- (E) [AC01] Given an employee, when they pick a date range, then the request is saved as pending.
- (E) [AC02] Given an existing request, when a new one overlaps it, then the new one is refused.

### FR-01.02 - Approve a request

- (E) [AC01] Given a pending request, when the manager approves it, then the employee sees it as approved.
"""
BRIEF_RECIPES = """## Functional Requirements

**FR-01.01: Save a recipe**
- [ ] Given a cook, when they enter a title and steps, then the recipe is saved.
- [ ] Given a recipe without a title, when it is saved, then it is refused with a clear message.

**FR-01.02: Search recipes**
- [ ] Given saved recipes, when the cook searches by ingredient, then matching recipes are listed.
"""
BROKEN = """### FR-01.01 - Reports and reminders

- (E) [AC01] Export the report to PDF.
- (E) [AC02] Given a booking, when it is posted via POST /api/bookings, then it is stored.
- (E) [AC03] Given a booking, when the file src/ledger.py is read, then the total is shown.
- (E) [AC04] Given a user, when the getUser() call returns, then the name is shown.

### FR-01.02 - Empty requirement
"""
SHOULD_MAY = """| ID | Area | Name | Priority | Description | Basis | Layers |
|----|------|------|----------|-------------|-------|--------|
| FR-01.01 | Auth | Sign in | Must | The system SHALL sign users in. | interview | unit |
| FR-01.02 | Auth | Remember me | May | The system MAY remember a user. | interview | unit |
| FR-01.03 | Auth | Login rate limit | Should | The system SHOULD limit sign-ins. | assumed | unit |
| FR-01.04 | Auth | Share to LinkedIn | Should | The system SHOULD post to LinkedIn or WordPress or TikTok. | interview | unit |

### FR-01.01 - Sign in

- [ ] A registered user can sign in with a password.
- [ ] Confirm the threshold with the product owner before build.

### FR-01.04 - Share to LinkedIn

- [ ] Given a post, when the user shares it to LinkedIn, then the post appears on WordPress and TikTok.

### Removed Requirements

| ID | Requirement | Priority | Removed by | status |
|----|-------------|----------|------------|--------|
| FR-01.09 | The system SHALL support social login | Must | iterate-20260120-drop-oauth | status: deprecated |
"""


@pytest.mark.covers("FR-01.02")
def test_two_brief_outputs_pass_the_form_checks():
    assert check_spec(BRIEF_LEAVE) == [] and check_spec(BRIEF_RECIPES) == []


@pytest.mark.covers("FR-01.02")
def test_only_paths_symbols_and_missing_criteria_block_everything_else_is_a_prompt():
    bad = {r["fr"]: r for r in check_spec(BROKEN)}
    blocking = " | ".join(bad["FR-01.01"]["problems"])
    assert "AC03: implementation detail (file-path)" in blocking and "AC04: implementation detail (code-symbol)" in blocking
    assert "AC01" not in blocking and "AC02" not in blocking  # shape and an HTTP verb are prompts only
    prompts = " | ".join(bad["FR-01.01"]["prompts"])
    assert "AC01: not in Given/when/then form" in prompts and "AC02: mentions http-verb" in prompts
    assert bad["FR-01.01"]["needs_capability_test"] is True and "name joins two capabilities" in prompts
    assert bad["FR-01.02"]["problems"] and "no acceptance criteria" in bad["FR-01.02"]["problems"][0]


@pytest.mark.covers("FR-01.02")
def test_prescribed_shapes_do_not_block_checkbox_criteria_should_may_without_criteria_brands_and_retired_rows():
    result = {r["fr"]: r for r in check_spec(SHOULD_MAY)}
    assert all(not r["problems"] for r in result.values())  # Should/May without criteria, checkbox criteria, LinkedIn/WordPress/TikTok
    assert "FR-01.09" not in result  # a retired row under Removed Requirements is skipped
    assert "FR-01.02" not in result and "FR-01.03" not in result  # lenient priority, no criteria: nothing to say
    assert result["FR-01.01"]["prompts"]  # the checkbox criteria are prompts at most
    no_criteria = SHOULD_MAY.replace(
        "- [ ] A registered user can sign in with a password.\n- [ ] Confirm the threshold with the product owner before build.\n", "")
    first = check_spec(no_criteria)[0]  # a Must requirement with no criteria at all blocks
    assert first["fr"] == "FR-01.01" and "no acceptance criteria" in first["problems"][0]


@pytest.mark.covers("FR-01.02")
def test_a_spec_with_text_but_no_readable_requirement_is_a_problem_not_a_pass(tmp_path, capsys):
    prose = "# Spec\n\nThe system will do things, but no requirement here is written in a shape this check can read.\n"
    assert check_spec(prose)[0]["problems"] == ["no requirement this check can read"]
    assert check_spec("")[0]["problems"] == ["no requirement this check can read"]  # an empty or blank spec is not a pass
    assert check_spec("  \n\n")[0]["problems"] == ["no requirement this check can read"]
    spec = tmp_path / "s.md"
    spec.write_text(prose, encoding="utf-8")
    assert cli.main(["--spec", str(spec)]) == 1
    assert "no requirement this check can read" in capsys.readouterr().out


@pytest.mark.covers("FR-01.02")
def test_cli_exits_one_on_a_problem_and_zero_when_clean(tmp_path, capsys):
    good, bad = tmp_path / "good.md", tmp_path / "bad.md"
    good.write_text(BRIEF_LEAVE, encoding="utf-8")
    bad.write_text(BROKEN, encoding="utf-8")
    assert cli.main(["--spec", str(good)]) == 0
    assert cli.main(["--spec", str(good), str(bad)]) == 1
    assert "FR-01.01" in capsys.readouterr().out


@pytest.mark.covers("FR-01.02")
def test_an_and_in_the_name_is_printed_but_does_not_change_the_exit_code(tmp_path, capsys):
    spec = tmp_path / "s.md"
    spec.write_text(BRIEF_LEAVE.replace("Request time off", "Request and cancel time off"), encoding="utf-8")
    assert check_spec(spec.read_text(encoding="utf-8"))[0]["problems"] == [] and cli.main(["--spec", str(spec)]) == 0
    assert cli.main(["--spec", str(spec)]) == 0
    out = capsys.readouterr().out
    assert "capability test" in out and "FR-01.01" in out


@pytest.mark.covers("FR-01.02")
def test_brief_outputs_yield_no_splittable_fr(tmp_path):
    from tools.fr_cluster_report import build_report
    for n, spec in enumerate((BRIEF_LEAVE, BRIEF_RECIPES)):
        root = tmp_path / str(n)
        (root / ".shipwright/planning/01-core").mkdir(parents=True)
        (root / ".shipwright/planning/01-core/spec.md").write_text(spec, encoding="utf-8")
        assert all(r["verdict"] != "yes" for r in build_report(root))  # nothing built yet: "no evidence", never a split


@pytest.mark.covers("FR-01.02")
def test_s5_reads_the_criteria_of_an_adopt_format_spec_without_an_acceptance_label(tmp_path):
    """Parser question of the atomic-frs brief: bare '- (E)' bullets under a '### FR-..' heading are read as criteria by S5."""
    from tools.verifiers.spec_checks import check_s5_fr_coherence
    (tmp_path / ".shipwright/planning/01-adopted").mkdir(parents=True)
    (tmp_path / ".shipwright/planning/01-adopted/spec.md").write_text(BRIEF_LEAVE, encoding="utf-8")
    assert check_s5_fr_coherence(tmp_path)["status"] == "PASS"


@pytest.mark.covers("FR-01.02")
def test_units_and_js_framework_names_are_not_paths_or_symbols():
    spec = """### FR-01.01 - Energy readout

- (E) [AC01] Given a meter reading of 12 kWh, when the page loads, then the value is shown in kWh.
- (E) [AC02] Given a 4 mL dose and a pH of 7, when the dose is saved, then both are stored.
- (E) [AC03] Given a battery of 3000 mAh, when it is below 20 percent, then the charge is flagged.
- (E) [AC04] Given a deployment on Node.js or Next.js, when the app starts, then the dashboard loads with Vue.js and D3.js charts.
"""
    assert all(not r["problems"] for r in check_spec(spec))


@pytest.mark.covers("FR-01.02")
def test_cli_reports_an_unreadable_file_cleanly_and_exits_one(tmp_path, capsys):
    assert cli.main(["--spec", str(tmp_path / "missing.md")]) == 1
    assert "cannot read" in capsys.readouterr().out
    binary = tmp_path / "bad.md"
    binary.write_bytes(b"\xff\xfe\x00broken")
    assert cli.main(["--spec", str(binary)]) == 1
    assert "cannot read" in capsys.readouterr().out
