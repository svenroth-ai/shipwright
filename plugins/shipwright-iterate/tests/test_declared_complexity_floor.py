"""A campaign unit's declared complexity is a FLOOR (FR-01.11/AC52).

The operator declares a unit `medium` in the campaign brief; the planner writes it
into the unit's sub-iterate spec as a `Complexity:` line. Stage 1 and the Step 3.4
re-check both read it back: the diff may raise the tier, never lower it. Before
this, a 113-178 line medium unit was classified `small` and its plan, architecture
and doubt reviews were closed not-applicable.

Real fixtures throughout: the real spec text the planner writes, the real
classifier, the real re-check CLI entry point (in-process). Subprocess composition
lives in integration-tests/test_campaign_declared_complexity_floor_integration.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent.parent / "scripts" / "lib"
TOOLS = Path(__file__).resolve().parent.parent / "scripts" / "tools"
for _p in (LIB, TOOLS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import campaign_init  # noqa: E402
import classify_complexity as cc  # noqa: E402
import declared_complexity as dc  # noqa: E402
import diff_risk_recheck as drr  # noqa: E402

INERT = ["plugins/x/profiles/rules.json", "plugins/x/lib/render.py"]
HOOK = "plugins/shipwright-iterate/hooks/hooks.json"
UNIT = {"id": "U1", "slug": "rule-format", "title": "Rule format", "scope": "Add a rule object.",
        "acceptance_criteria": "- [ ] All bundled profiles validate"}


def _spec(root: Path, complexity=None) -> Path:
    unit = dict(UNIT, **({"complexity": complexity} if complexity else {}))
    campaign_init.init_campaign(root, "camp", "intent", [unit])
    return root / ".shipwright/planning/iterate/campaigns/camp/sub-iterates/U1-rule-format.md"


# -- parsing ---------------------------------------------------------------


@pytest.mark.covers("FR-01.11/AC52")
@pytest.mark.parametrize("line", [
    "Complexity: medium", "complexity: MEDIUM", "**Complexity:** medium",
    "- Complexity: medium", "Complexity: **medium**", "  Complexity:medium  ",
])
def test_parse_accepts_the_declaring_line(line):
    assert dc.parse_declared_complexity(f"# Unit\n\n{line}\n\n## Scope\n") == "medium"


@pytest.mark.covers("FR-01.11/AC52")
@pytest.mark.parametrize("text", [
    None, "", "# Unit\n\n## Scope\nno declaration\n",
    "The Complexity: small changes are fine here\n",   # prose, not the declaring line
    "complexity small\n",
])
def test_parse_declares_nothing_for_prose_or_unknown(text):
    assert dc.parse_declared_complexity(text) is None


@pytest.mark.covers("FR-01.11/AC52")
def test_a_typo_in_the_level_is_an_error_not_a_silently_dropped_floor(tmp_path):
    with pytest.raises(ValueError, match="gigantic"):
        dc.parse_declared_complexity("# U\n\nComplexity: gigantic\n")
    spec = tmp_path / "u.md"
    spec.write_text("Complexity: mediun\n", encoding="utf-8")
    with pytest.raises(ValueError):
        dc.read_declared_complexity(spec)


@pytest.mark.covers("FR-01.11/AC52")
def test_first_declaring_line_wins_over_a_later_quotation():
    assert dc.parse_declared_complexity("Complexity: medium\n\nExample:\nComplexity: small\n") == "medium"


@pytest.mark.covers("FR-01.11/AC52")
def test_an_unreadable_spec_path_is_an_error_but_no_path_declares_nothing(tmp_path):
    with pytest.raises(OSError):
        dc.read_declared_complexity(tmp_path / "missing.md")
    assert dc.read_declared_complexity(None) is None


@pytest.mark.covers("FR-01.11/AC52")
def test_apply_floor_compares_by_rank_not_string_order():
    assert dc.apply_floor("small", "medium") == "medium"
    assert dc.apply_floor("large", "medium") == "large"
    assert dc.apply_floor("small", None) == "small"


# -- the planner writes it, the readers find it -----------------------------


@pytest.mark.covers("FR-01.11/AC52")
def test_planner_emits_the_line_and_it_round_trips(tmp_path):
    spec = _spec(tmp_path, "medium")
    assert "\nComplexity: medium\n" in spec.read_text(encoding="utf-8")
    assert dc.read_declared_complexity(spec) == "medium"


@pytest.mark.covers("FR-01.11/AC52")
def test_planner_without_complexity_writes_the_unchanged_spec(tmp_path):
    text = _spec(tmp_path).read_text(encoding="utf-8")
    assert "Complexity" not in text
    assert text.startswith("# Sub-Iterate: U1 — Rule format\n\n## Scope")


@pytest.mark.covers("FR-01.11/AC52")
def test_planner_rejects_an_unknown_tier_in_any_unit_before_writing_anything(tmp_path):
    second = dict(UNIT, id="U2", slug="two", complexity="gigantic")
    with pytest.raises(ValueError, match="U2.*gigantic"):
        campaign_init.init_campaign(tmp_path, "camp", "i", [dict(UNIT, complexity="medium"), second])
    assert not (tmp_path / ".shipwright").exists()


# -- Stage 1 ---------------------------------------------------------------


def _classify_cli(monkeypatch, capsys, *argv) -> tuple[int, dict]:
    monkeypatch.setattr(sys, "argv", ["classify_complexity.py", *argv])
    try:
        cc.main()
        code = 0
    except SystemExit as exc:
        code = int(exc.code or 0)
    out = capsys.readouterr().out
    return code, (json.loads(out) if out.strip() else {})


@pytest.mark.covers("FR-01.11/AC52")
def test_stage1_declared_medium_stays_medium_for_a_small_message(tmp_path, monkeypatch, capsys):
    declared = _spec(tmp_path / "a", "medium")
    undeclared = _spec(tmp_path / "b")
    msg = undeclared.read_text(encoding="utf-8")
    code, out = _classify_cli(monkeypatch, capsys, "--message", msg, "--spec", str(declared))
    assert code == 0 and out["estimate"] == "medium"
    assert out["signals"]["declared_complexity"] == "medium"
    code, out = _classify_cli(monkeypatch, capsys, "--message", msg, "--spec", str(undeclared))
    assert code == 0 and out["estimate"] != "medium"          # the declaration is what raised it
    assert out["signals"]["declared_complexity"] is None


@pytest.mark.covers("FR-01.11/AC52")
def test_stage1_declared_floor_can_still_be_raised():
    big = cc.classify("rewrite the whole thing from scratch", declared_complexity="small")
    assert big["estimate"] == "large"
    flagged = cc.classify("refactor the stripe webhook handler", declared_complexity="trivial")
    assert flagged["estimate"] == "small"                    # touches_billing floors at small


@pytest.mark.covers("FR-01.11/AC52")
def test_stage1_without_declaration_is_unchanged():
    msg = "fix a typo in the readme"
    out = cc.classify(msg)
    assert out["signals"]["declared_complexity"] is None
    assert out["estimate"] == cc.classify(msg, declared_complexity=None)["estimate"]


@pytest.mark.covers("FR-01.11/AC52")
def test_stage1_a_declaration_quoted_in_a_message_is_not_a_floor():
    out = cc.classify("Complexity: large\n\nfix a typo")
    assert out["estimate"] != "large" and out["signals"]["declared_complexity"] is None


@pytest.mark.covers("FR-01.11/AC52")
def test_stage1_rejects_an_unknown_floor_with_a_named_error():
    with pytest.raises(ValueError, match="huge"):
        cc.classify("fix a typo", declared_complexity="huge")


@pytest.mark.covers("FR-01.11/AC52")
@pytest.mark.parametrize("header", [
    "# U\n\nComplexity: mediun\n\nComplexity: small\n",         # typo is not papered over by a later valid line
    "# U\n\nComplexity: medium.\n",                              # trailing punctuation is not a clean level
])
def test_the_first_declaring_header_line_decides_and_must_be_clean(header):
    with pytest.raises(ValueError):
        dc.parse_declared_complexity(header)


@pytest.mark.covers("FR-01.11/AC52")
def test_tab_separated_declaration_is_read():
    assert dc.parse_declared_complexity("# U\n\nComplexity:\tmedium\n") == "medium"


@pytest.mark.covers("FR-01.11/AC52")
def test_only_the_header_declares_so_scope_prose_cannot_raise_or_fail_a_unit():
    body = "# U\n\n## Scope\n\nComplexity: large\n- complexity: quadratic\n\n## Acceptance Criteria\n"
    assert dc.parse_declared_complexity(body) is None
    declared = "# U\n\nComplexity: medium\n\n## Scope\n\nComplexity: small\n"
    assert dc.parse_declared_complexity(declared) == "medium"


@pytest.mark.covers("FR-01.11/AC52")
def test_stage1_cli_stops_on_an_unreadable_spec(tmp_path, monkeypatch, capsys):
    code, _ = _classify_cli(monkeypatch, capsys, "--message", "x", "--spec", str(tmp_path / "nope.md"))
    assert code == 2


# -- Step 3.4 re-check -----------------------------------------------------


@pytest.mark.covers("FR-01.11/AC52")
def test_recheck_declared_medium_with_a_100_line_inert_diff_stays_medium():
    out = drr.recheck(INERT, "small", diff_loc=113, declared_complexity="medium")
    assert out["effective_complexity"] == "medium"
    assert out["declared_complexity"] == "medium"
    assert out["upgraded"] is True
    assert out["plan_review_required"] is True


@pytest.mark.covers("FR-01.11/AC52")
def test_recheck_declared_medium_beats_a_stale_low_stage1():
    out = drr.recheck(INERT, "trivial", diff_loc=3, declared_complexity="medium")
    assert out["effective_complexity"] == "medium"


@pytest.mark.covers("FR-01.11/AC52")
def test_recheck_declared_medium_is_a_floor_not_a_pin():
    assert drr.recheck(INERT, "large", declared_complexity="medium")["effective_complexity"] == "large"


@pytest.mark.covers("FR-01.11/AC52")
def test_recheck_declared_small_is_still_raised_by_the_diff():
    out = drr.recheck([HOOK], "small", diff_loc=10, declared_complexity="small")
    assert out["effective_complexity"] == "medium"
    assert out["complexity_floor"] == "medium"


@pytest.mark.covers("FR-01.11/AC52")
def test_recheck_without_declaration_keeps_todays_behaviour():
    out = drr.recheck(INERT, "small", diff_loc=113)
    assert out["effective_complexity"] == "small"
    assert out["declared_complexity"] is None
    assert out["upgraded"] is False


@pytest.mark.covers("FR-01.11/AC52")
def test_recheck_rejects_an_unknown_declared_tier():
    with pytest.raises(ValueError, match="declared"):
        drr.recheck(INERT, "small", declared_complexity="huge")


@pytest.mark.covers("FR-01.11/AC52")
def test_cli_reads_the_spec_and_persists_the_declared_tier(tmp_path, monkeypatch, capsys):
    spec = _spec(tmp_path, "medium")
    run_id = "iterate-2026-11-16-u1-example"
    monkeypatch.setattr(sys, "argv", [
        "diff_risk_recheck.py", "--project-root", str(tmp_path),
        "--changed-files", "\n".join(INERT), "--diff-loc", "113",
        "--stage1-complexity", "small", "--run-id", run_id, "--spec", str(spec),
    ])
    assert drr.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["effective_complexity"] == "medium"
    record = json.loads((tmp_path / ".shipwright/planning/iterate" / run_id
                         / "risk_recheck.json").read_text(encoding="utf-8"))
    assert record["risk_recheck"]["declared_complexity"] == "medium"
    assert record["risk_recheck"]["effective_complexity"] == "medium"


@pytest.mark.covers("FR-01.11/AC52")
def test_planner_rejects_large_which_the_runner_would_stop_on(tmp_path):
    with pytest.raises(ValueError, match="large"):
        campaign_init.init_campaign(tmp_path, "camp", "i", [dict(UNIT, complexity="large")])


@pytest.mark.covers("FR-01.11/AC52")
def test_cli_stops_on_an_unreadable_spec(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "diff_risk_recheck.py", "--project-root", str(tmp_path), "--changed-files", INERT[0],
        "--diff-loc", "5", "--stage1-complexity", "small", "--spec", str(tmp_path / "nope.md"),
    ])
    assert drr.main() == 2
    assert "error" in json.loads(capsys.readouterr().out)
