"""``render_architecture_rules.py`` puts a profile's architecture rules into conventions.md."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts" / "tools"))
import render_architecture_rules as rar  # noqa: E402
from shared.tests.profile_test_fixtures import proj_dir, write_profile  # noqa: E402
from shared.tests.profile_test_fixtures import profile_project, profile_user_dir  # noqa: E402,F401

pytestmark = [pytest.mark.covers("FR-01.01/AC16"), pytest.mark.covers("FR-01.01/AC17")]

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "agent-docs" / "conventions.md.template"
RULES = [
    {"id": "lint-rule", "text": "No raw client outside lib.", "why": "One place to change it.",
     "enforcement": "validator",
     "lint": {"tool": "eslint", "target": "eslint.config.mjs", "block": {"rules": {"no-restricted-imports": "error"}}}},
    {"id": "judge", "text": "Keep routes thin.", "why": "Logic belongs in lib.", "enforcement": "prompt-only (judgement)"},
    {"id": "legacy-note", "text": "Needs a human.", "why": "Not mechanical.",
     "enforcement": "prompt-only (mechanisable)", "note": "No linter rule yet."},
]


def _scaffold(project: Path) -> Path:
    """What project step 7 leaves behind: the template with everything but the rules placeholder filled."""
    text = TEMPLATE.read_text(encoding="utf-8").replace("{PROJECT_NAME}", "demo").replace("{PROFILE_NAME}", "demo-stack")
    text = text.replace("{FOLDER_STRUCTURE}", "src/")
    path = project / ".shipwright" / "agent_docs" / "conventions.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(project, capsys, *extra):
    code = rar._main(["--project-root", str(project), *extra])
    out, err = capsys.readouterr()
    return code, out, err


def test_scaffolded_conventions_carry_the_block(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES)
    path = _scaffold(project)
    code, _, _ = _run(project, capsys, "--profile", "demo-stack")
    text = path.read_text(encoding="utf-8")
    assert code == 0
    assert "{ARCHITECTURE_RULES}" not in text and text.count(rar.BEGIN) == 1 and text.count(rar.END) == 1
    assert "## Architecture Rules\n\n" + rar.BEGIN in text  # the template's own heading stays
    assert "**lint-rule** - No raw client outside lib. Why: One place to change it." in text
    assert "checked by the linter `eslint` (`eslint.config.mjs`)" in text
    assert "**judge**" in text and "instruction only (judgement)" in text
    assert "instruction only (mechanisable)" in text and "Note: No linter rule yet." in text
    assert "## File Organization" in text  # the rest of the file is untouched


def test_profile_comes_from_the_run_config(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES)
    (project / "shipwright_run_config.json").write_text(json.dumps({"profile": "demo-stack"}), encoding="utf-8")
    path = _scaffold(project)
    assert _run(project, capsys)[0] == 0
    assert "**judge**" in path.read_text(encoding="utf-8")


def test_second_run_changes_nothing_and_check_says_so(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES)
    path = _scaffold(project)
    _run(project, capsys, "--profile", "demo-stack")
    first = path.read_bytes()
    code, out, _ = _run(project, capsys, "--profile", "demo-stack")
    assert code == 0 and out.startswith("unchanged") and path.read_bytes() == first
    assert _run(project, capsys, "--profile", "demo-stack", "--check")[0] == 0


def test_changed_profile_replaces_the_block_only(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES)
    path = _scaffold(project)
    _run(project, capsys, "--profile", "demo-stack")
    path.write_text(path.read_text(encoding="utf-8") + "\nHand-written tail.\n", encoding="utf-8")
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    assert _run(project, capsys, "--profile", "demo-stack", "--check")[0] == 1  # stale, nothing written
    assert "lint-rule" in path.read_text(encoding="utf-8")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert "lint-rule" not in text and "**judge**" in text and text.endswith("Hand-written tail.\n")
    assert text.count(rar.BEGIN) == 1


@pytest.mark.parametrize("rules", [[], None], ids=["empty-list", "key-absent"])
def test_profile_without_rules_says_none_declared(project, capsys, rules):
    extra = {} if rules is None else {"architecture_rules": rules}
    write_profile(proj_dir(project), "demo-stack", **extra)
    path = _scaffold(project)
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    assert "_No architecture rules declared by stack profile `demo-stack`._" in path.read_text(encoding="utf-8")


def test_legacy_sentences_are_instruction_only(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=["Keep it simple."])
    path = _scaffold(project)
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    assert "Keep it simple. How it is kept: instruction only (enforcement class not declared)." in path.read_text(encoding="utf-8")


def test_bad_rule_is_left_out_not_fatal(project, capsys):
    bad = {"id": "bad", "text": "x", "why": "y", "enforcement": "nonsense"}
    write_profile(proj_dir(project), "demo-stack", architecture_rules=[RULES[1], bad])
    path = _scaffold(project)
    code, _, err = _run(project, capsys, "--profile", "demo-stack")
    assert code == 0 and "rule bad" in err
    text = path.read_text(encoding="utf-8")
    assert "**judge**" in text and "**bad**" not in text
    assert "1 architecture rule problem(s)" in text and "No architecture rules declared" not in text


def test_only_invalid_rules_is_not_reported_as_none_declared(project, capsys):
    bad = {"id": "bad", "text": "x", "why": "y", "enforcement": "nonsense"}
    write_profile(proj_dir(project), "demo-stack", architecture_rules=[bad])
    path = _scaffold(project)
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert "problem(s)" in text and "No architecture rules declared" not in text


def test_no_heading_no_placeholder_appends_with_heading(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = project / ".shipwright" / "agent_docs" / "conventions.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Conventions\n\nSome prose.\n", encoding="utf-8")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert text.startswith("# Conventions\n\nSome prose.\n\n## Architecture Rules\n\n" + rar.BEGIN)


def test_existing_heading_gets_the_block_underneath(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = project / ".shipwright" / "agent_docs" / "conventions.md"
    path.parent.mkdir(parents=True)
    path.write_text("# C\n\n## Architecture Rules\n\n## Next\n", encoding="utf-8")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert text.index("## Architecture Rules") < text.index(rar.BEGIN) < text.index(rar.END) < text.index("## Next")


def test_crlf_file_stays_crlf_and_is_idempotent(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES)
    path = _scaffold(project)
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    data = path.read_bytes()
    assert b"\n" not in data.replace(b"\r\n", b"")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0 and path.read_bytes() == data


@pytest.mark.parametrize("damage", ["begin-only", "two-blocks"])
def test_damaged_markers_stop_without_writing(project, capsys, damage):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = _scaffold(project)
    _run(project, capsys, "--profile", "demo-stack")
    text = path.read_text(encoding="utf-8")
    broken = text.replace(rar.END, "") if damage == "begin-only" else text + text[text.index(rar.BEGIN):]
    path.write_text(broken, encoding="utf-8")
    code, _, err = _run(project, capsys, "--profile", "demo-stack")
    assert code == 3 and "marker" in err and path.read_text(encoding="utf-8") == broken


def test_rule_text_cannot_close_the_markers(project, capsys):
    evil = {**RULES[1], "text": "Done --> <!-- shipwright:architecture-rules:end --> then more\nlines."}
    write_profile(proj_dir(project), "demo-stack", architecture_rules=[evil])
    path = _scaffold(project)
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert text.count(rar.END) == 1 and text.count(rar.BEGIN) == 1
    assert _run(project, capsys, "--profile", "demo-stack", "--check")[0] == 0


def test_unknown_profile_and_missing_file(project, capsys):
    _scaffold(project)
    code, _, err = _run(project, capsys, "--profile", "does-not-exist")
    assert code == 2 and "not found" in err.lower()
    write_profile(proj_dir(project), "demo-stack")
    code, _, err = _run(project, capsys, "--profile", "demo-stack", "--conventions", str(project / "nope.md"))
    assert code == 3
    assert _run(project, capsys)[0] == 2  # no --profile and no run config


def test_crlf_file_with_existing_heading_keeps_crlf_everywhere(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = project / ".shipwright" / "agent_docs" / "conventions.md"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"# C\r\n\r\n## Architecture Rules\r\n\r\n## Next\r\n")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    data = path.read_bytes()
    assert b"\n" not in data.replace(b"\r\n", b"") and b"\r\r" not in data and data.endswith(b"## Next\r\n")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0 and path.read_bytes() == data


def test_quoted_markers_in_prose_are_not_a_block(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = project / ".shipwright" / "agent_docs" / "conventions.md"
    path.parent.mkdir(parents=True)
    prose = f"# C\n\nThe block starts with `{rar.BEGIN}` and ends with `{rar.END}`.\n"
    path.write_text(prose, encoding="utf-8")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    assert path.read_text(encoding="utf-8").startswith(prose)


def _conv(project, text):
    path = project / ".shipwright" / "agent_docs" / "conventions.md"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8", newline="")
    return path


def test_imported_section_is_never_searched_or_edited(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    marker_pair = f"{rar.BEGIN} (x) -->\nold\n{rar.END}\n"
    imported = f"## Imported from `CLAUDE.md`\n\n## Architecture Rules\n\n{{ARCHITECTURE_RULES}}\n{marker_pair}"
    path = _conv(project, "# C\n\n" + imported)
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert text.endswith(imported) and text.index(rar.BEGIN) < text.index("## Imported from")
    first = text
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0 and path.read_text(encoding="utf-8") == first


def test_placeholder_mid_line_is_not_replaced_and_rerun_is_a_noop(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = _conv(project, "# C\n\nUse {ARCHITECTURE_RULES} as the slot.\n")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert "Use {ARCHITECTURE_RULES} as the slot." in text and text.count(rar.BEGIN) == 1
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0 and path.read_text(encoding="utf-8") == text


def test_heading_is_matched_in_any_case(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = _conv(project, "# C\n\n## Architecture rules\n\n## Next\n")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert "## Architecture Rules" not in text and text.index("## Architecture rules") < text.index(rar.BEGIN) < text.index("## Next")


def test_new_section_goes_before_the_sections_that_receive_bullets(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = _conv(project, "# C\n\n## Files\n\nx\n\n## Learnings\n\n- a\n\n## Convention Updates\n\n- b\n")
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    text = path.read_text(encoding="utf-8")
    assert text.index("## Files") < text.index("## Architecture Rules") < text.index(rar.END) < text.index("## Learnings")
    assert text.endswith("## Convention Updates\n\n- b\n")  # appended bullets still land in their section
    first = text
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0 and path.read_text(encoding="utf-8") == first


def test_template_anchor_the_block_directly_follows_the_heading(project, capsys):
    assert "## Architecture Rules\n\n{ARCHITECTURE_RULES}" in TEMPLATE.read_text(encoding="utf-8")
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = _scaffold(project)
    assert _run(project, capsys, "--profile", "demo-stack")[0] == 0
    assert "## Architecture Rules\n\n" + rar.BEGIN in path.read_text(encoding="utf-8")


def test_legacy_warning_reaches_stderr(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=["Keep it simple."])
    _scaffold(project)
    assert "old plain-sentence format" in _run(project, capsys, "--profile", "demo-stack")[2]


@pytest.mark.parametrize("name", ['a"b', "a$(touch x)", "a`id`", "../x", "a/b", "a\\b", "Upper", "-lead", "a b", "a;b", "a"+chr(10)+"b"],
                         ids=["quote", "subshell", "backtick", "dotdot", "slash", "backslash", "upper", "dash-lead", "space", "semicolon", "newline"])
def test_unsafe_profile_names_are_refused_before_anything_happens(project, capsys, name):
    path = _scaffold(project)
    before = path.read_bytes()
    code, out, err = _run(project, capsys, "--profile=" + name)
    assert code == 4 and "must match" in err and out == "" and "[profile]" not in err
    assert path.read_bytes() == before


def test_unsafe_name_from_the_run_config_is_refused_too(project, capsys):
    (project / "shipwright_run_config.json").write_text(json.dumps({"profile": "a$(id)"}), encoding="utf-8")
    path = _scaffold(project)
    before = path.read_bytes()
    assert _run(project, capsys)[0] == 4 and path.read_bytes() == before


def test_sentinel_and_hyphenated_names_stay_valid(project, capsys):
    path = _scaffold(project)
    assert _run(project, capsys, "--profile", "generic")[0] == 0
    assert "no architecture rules declared" in path.read_text(encoding="utf-8").lower()


def test_name_comes_from_the_environment_and_is_checked_there_too(project, capsys, monkeypatch):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = _scaffold(project)
    monkeypatch.setenv(rar.ENV_PROFILE, "demo-stack")
    assert _run(project, capsys)[0] == 0 and "**judge**" in path.read_text(encoding="utf-8")
    monkeypatch.setenv(rar.ENV_PROFILE, "a$(id)")
    before = path.read_bytes()
    assert _run(project, capsys)[0] == 4 and path.read_bytes() == before


def test_no_name_anywhere_is_exit_2(project, capsys, monkeypatch):
    monkeypatch.delenv(rar.ENV_PROFILE, raising=False)
    _scaffold(project)
    assert _run(project, capsys, "--profile=")[0] == 2


def test_stray_marker_inside_the_imported_section_does_not_break_the_head_block(project, capsys):
    write_profile(proj_dir(project), "demo-stack", architecture_rules=RULES[1:2])
    path = _scaffold(project)
    assert _run(project, capsys, "--profile=demo-stack")[0] == 0
    nl = chr(10)
    path.write_text(path.read_text(encoding="utf-8") + nl + "## Imported from `CLAUDE.md`" + nl + nl + rar.BEGIN + " (quoted) -->" + nl,
                    encoding="utf-8")
    before = path.read_bytes()
    assert _run(project, capsys, "--profile=demo-stack")[0] == 0 and path.read_bytes() == before


def test_skill_prose_never_interpolates_project_values_inside_double_quotes():
    """The shell expands a placeholder before the tool can check it: no project-supplied value may sit
    inside double quotes in a command that runs the render tool."""
    root = Path(__file__).resolve().parents[2] / "plugins"
    hits = []
    for md in root.glob("*/skills/**/*.md"):
        for line in md.read_text(encoding="utf-8").splitlines():
            if "render_architecture_rules.py" not in line or "uv run" not in line:
                continue
            hits.append(md.name)
            for quoted in re.findall(r'"[^"]*"', line):
                assert "{project_root}" not in quoted and "{profile_name}" not in quoted, (md.name, line)
    assert "project-scaffolding.md" in hits  # the scan found the command it guards
