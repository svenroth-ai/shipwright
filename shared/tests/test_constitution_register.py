"""Drift guard: every rule of shared/constitution.md is declared in the enforcement register, and the generated doc is current.

A rule added, reworded or removed in the constitution without touching the register fails here. If the doc is stale:

    uv run shared/scripts/tools/constitution_register.py --render > shared/config/constitution_register.md
"""
from __future__ import annotations

from pathlib import Path

import pytest

from lib import constitution_register as cr

pytestmark = pytest.mark.covers("FR-01.11")  # tooling for the constitution; no AC is claimed

ROOT = Path(__file__).resolve().parents[2]
CONSTITUTION = ROOT / "shared" / "constitution.md"
CONVENTIONS = ROOT / "shared" / "config" / "conventions.json"
DOC = ROOT / "shared" / "config" / "constitution_register.md"


def _rules() -> list[cr.Rule]:
    return cr.parse_rules(CONSTITUTION.read_text(encoding="utf-8"))


def test_every_rule_is_declared_and_every_declaration_matches() -> None:
    problems = cr.check(_rules(), cr.load_register(CONVENTIONS), ROOT)
    assert problems == [], "constitution register drift:\n" + "\n".join(problems)


def test_parser_finds_every_tier() -> None:
    assert {r.tier for r in _rules()} == set(cr.TIERS)


def test_generated_doc_is_current_and_beside_its_source() -> None:
    assert DOC.parent == CONVENTIONS.parent
    expected = cr.render_markdown(cr.load_register(CONVENTIONS)) + "\n"
    assert DOC.read_text(encoding="utf-8") == expected, "stale; run constitution_register.py --render"


RULE_TEXT = "# C\n\n## ALWAYS\n\n- Do the thing\n  continued\n- Other thing\n\n## NEVER\n\n- Bad thing\n"


def _entry(rule: cr.Rule, **kw) -> dict:
    return {"id": kw.pop("id", rule.text_hash), "tier": rule.tier, "text_hash": rule.text_hash,
            "enforcement": "prompt-only (judgement)", "mechanism": [], **kw}


def test_parser_joins_continuation_lines_and_splits_bullets() -> None:
    rules = cr.parse_rules(RULE_TEXT)
    assert [(r.tier, r.text) for r in rules] == [("always", "- Do the thing continued"), ("always", "- Other thing"), ("never", "- Bad thing")]


def test_check_reports_undeclared_reworded_and_bad_vocabulary(tmp_path: Path) -> None:
    rules = cr.parse_rules(RULE_TEXT)
    register = [_entry(rules[0]), _entry(rules[1], enforcement="magic"), {**_entry(rules[2]), "text_hash": "deadbeef0000"}]
    problems = "\n".join(cr.check(rules, register, tmp_path))
    assert "not in the closed vocabulary" in problems
    assert "no rule has text_hash deadbeef0000" in problems
    assert "undeclared rule [never]" in problems


def test_check_demands_a_real_mechanism_for_hook_validator_test(tmp_path: Path) -> None:
    rules = cr.parse_rules(RULE_TEXT)[:1]
    assert any("names no mechanism" in p for p in cr.check(rules, [_entry(rules[0], enforcement="hook")], tmp_path))
    assert any("does not exist" in p for p in cr.check(rules, [_entry(rules[0], enforcement="hook", mechanism=["nope.py"])], tmp_path))
    (tmp_path / "ok.py").write_text("", encoding="utf-8")
    assert cr.check(rules, [_entry(rules[0], enforcement="validator", mechanism=["ok.py"])], tmp_path) == []


def test_parser_reports_lines_and_sections_it_cannot_place() -> None:
    _, strays = cr.parse("## ALWAYS\n\n- Rule one\nlazy continuation\n\n## Brand New Tier\n\n- hidden rule\n\n## Programmatic Enforcement\n\nprose\n")
    assert any("unplaced line: lazy continuation" in s for s in strays)
    assert any("unknown section heading: ## Brand New Tier" in s for s in strays)
    assert not any("Programmatic" in s for s in strays)
    assert cr.parse(CONSTITUTION.read_text(encoding="utf-8"))[1] == []


def test_check_carries_the_strays_and_two_identical_rules(tmp_path: Path) -> None:
    rules = cr.parse_rules("## ALWAYS\n\n- Same\n- Same\n")
    problems = cr.check(rules, [_entry(rules[0])], tmp_path, ["stray one"])
    assert "stray one" in problems
    assert any("same text" in p for p in problems)


def test_check_survives_an_entry_without_required_keys(tmp_path: Path) -> None:
    rules = cr.parse_rules(RULE_TEXT)
    assert any("lacks text_hash" in p for p in cr.check(rules, [{"id": "x", "tier": "always", "enforcement": "hook"}], tmp_path))


def test_a_hook_entry_must_be_registered_and_paths_must_stay_in_the_repo(tmp_path: Path) -> None:
    rules = cr.parse_rules(RULE_TEXT)[:1]
    (tmp_path / "unreg.py").write_text("", encoding="utf-8")
    assert any("registered in a plugin hooks.json" in p for p in cr.check(rules, [_entry(rules[0], enforcement="hook", mechanism=["unreg.py"])], tmp_path))
    hooks = tmp_path / "plugins" / "p" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").write_text('{"command": "uv run ${ROOT}/scripts/unreg.py"}', encoding="utf-8")
    assert cr.check(rules, [_entry(rules[0], enforcement="hook", mechanism=["unreg.py"])], tmp_path) == []
    assert any("repo-relative" in p for p in cr.check(rules, [_entry(rules[0], mechanism=["../x.py"])], tmp_path))


def test_cli_check_write_and_render(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scripts.tools import constitution_register as cli

    assert cli.main(["--check"]) == 0
    assert cli.main(["--render"]) == 0
    assert capsys.readouterr().out.startswith("# Constitution enforcement register")
    assert cli.main(["--check", "--repo-root", str(tmp_path)]) == 2  # no files there


def test_check_rejects_duplicate_hash_and_tier_mismatch(tmp_path: Path) -> None:
    rules = cr.parse_rules(RULE_TEXT)[:1]
    a, b = _entry(rules[0], id="a"), _entry(rules[0], id="b")
    assert any("declared twice" in p for p in cr.check(rules, [a, b], tmp_path))
    assert any("declared as tier" in p for p in cr.check(rules, [{**a, "tier": "never"}], tmp_path))
