"""``resolve_profile.py validate`` reports architecture-rule problems; nothing else does."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "tools"))
import resolve_profile as cli  # noqa: E402
import profile_resolver as pr  # noqa: E402
from shared.tests.profile_test_fixtures import proj_dir, write_profile  # noqa: E402
from shared.tests.profile_test_fixtures import profile_project, profile_user_dir  # noqa: E402,F401

pytestmark = pytest.mark.covers("FR-01.01/AC13")

GOOD = {"id": "r1", "text": "A.", "why": "B.", "enforcement": "prompt-only (judgement)"}


def _run(capsys, *argv):
    code = cli.main(list(argv))
    out, err = capsys.readouterr()
    return code, out, err


def _validate_json(capsys, project, name):
    code, out, err = _run(capsys, "validate", "--project-root", str(project), "--name", name, "--json")
    return code, json.loads(out), err


@pytest.mark.covers("FR-01.01/AC14")
def test_legacy_profile_warns_only_in_validate(project, capsys):
    write_profile(proj_dir(project), "legacy-one", architecture_rules=["Keep it simple", "Keep it small"])
    code, data, err = _validate_json(capsys, project, "legacy-one")
    assert code == 0 and data["valid"] is True and data["rule_errors"] == []
    assert len(data["rule_warnings"]) == 1 and "old plain-sentence" in err
    # ordinary resolution of the same profile prints no rule diagnostics at all
    code, out, err = _run(capsys, "resolve", "--project-root", str(project), "--name", "legacy-one")
    assert code == 0 and "plain-sentence" not in out + err and "architecture_rules" not in out + err
    res = pr.resolve_profile("legacy-one", project)
    assert [w for w in res.warnings if "plain-sentence" in w] == []


@pytest.mark.covers("FR-01.01/AC15")
def test_lint_plus_mechanism_rule_is_reported_but_profile_stays_valid(project, capsys):
    bad = {**GOOD, "id": "both", "enforcement": "validator", "mechanism": ["a.py"],
           "lint": {"tool": "eslint", "target": "e.mjs", "block": {"rules": {"no-restricted-imports": "error"}}}}
    write_profile(proj_dir(project), "custom-one", architecture_rules=[GOOD, bad])
    code, data, _ = _validate_json(capsys, project, "custom-one")
    assert code == 0 and data["valid"] is True
    assert len(data["rule_errors"]) == 1
    assert "rule both" in data["rule_errors"][0]
    assert "never both" in data["rule_errors"][0]
    # the profile still resolves for every other phase
    assert pr.resolve_profile("custom-one", project).data["architecture_rules"][0]["id"] == "r1"


def test_wrong_top_level_type_is_phase_local(project, capsys):
    write_profile(proj_dir(project), "custom-two", architecture_rules={"oops": 1})
    code, data, _ = _validate_json(capsys, project, "custom-two")
    assert code == 0 and "must be a list" in data["rule_errors"][0]
    assert pr.resolve_profile("custom-two", project).name == "custom-two"


def test_project_profile_paths_are_checked_against_project_root(project, capsys):
    (project / "tools").mkdir()
    (project / "tools" / "ok.py").write_text("", encoding="utf-8")
    rules = [{**GOOD, "id": "ok", "enforcement": "test", "mechanism": ["tools/ok.py"]},
             {**GOOD, "id": "gone", "enforcement": "test", "mechanism": ["tools/missing.py"]}]
    write_profile(proj_dir(project), "custom-three", architecture_rules=rules)
    _, data, err = _validate_json(capsys, project, "custom-three")
    assert len(data["rule_errors"]) == 1
    assert data["rule_errors"][0].startswith("architecture_rules: rule gone: mechanism 'tools/missing.py' does not exist")
    assert "error: architecture_rules: rule gone" in err


def test_shadow_warning_only_when_bundled_has_rules(project, capsys):
    write_profile(proj_dir(project), "supabase-nextjs", testing={"command": "x"})
    write_profile(proj_dir(project), "vite-hono", testing={"command": "x"})
    sup = pr.resolve_profile("supabase-nextjs", project)
    assert sup.warnings[0].startswith("WARNING: project profile") and "shadows the bundled profile 'supabase-nextjs'" in sup.warnings[0]
    assert len(sup.warnings) == 2 and "declares 6" in sup.warnings[1]  # exact order: shadow first, rules second
    vite = pr.resolve_profile("vite-hono", project)  # bundled list is empty: no rules warning
    assert len(vite.warnings) == 1


def test_explicit_empty_list_in_shadowing_profile_is_not_warned(project):
    write_profile(proj_dir(project), "supabase-nextjs", architecture_rules=[])
    assert len(pr.resolve_profile("supabase-nextjs", project).warnings) == 1


@pytest.mark.parametrize("name", pr.bundled_names())
def test_validate_every_bundled_profile_has_no_rule_errors(project, capsys, name):
    code, data, _ = _validate_json(capsys, project, name)
    assert code == 0 and data["rules_valid"] is True and data["rule_errors"] == []


def test_control_characters_in_rule_text_do_not_reach_the_terminal(project, capsys):
    esc = chr(27)
    write_profile(proj_dir(project), "custom-four", architecture_rules=[{**GOOD, "id": "ok" + esc + "[31m"}])
    _, _, err = _run(capsys, "validate", "--project-root", str(project), "--name", "custom-four")
    assert esc not in err and "rule 'ok" in err
