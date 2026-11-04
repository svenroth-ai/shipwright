"""In-process tests for lib/plan_design_check.py (the CLI tests run it in a subprocess)."""
import json
import pytest

from lib import plan_design_check as pdc

pytestmark = pytest.mark.covers("FR-01.05/AC05")

SCREEN = (
    '<html><style>@media (max-width: 900px){.a{color:#0d9488}}</style><body>'
    '<button aria-label="Previous thread">&lsaquo;</button><h1>Thread board</h1></body></html>'
)


def _cfg(root, **c):
    (root / "shipwright_run_config.json").write_text(json.dumps(c), encoding="utf-8")


@pytest.mark.parametrize("cfg,expected", [
    ({"autonomy": "guided"}, False),
    ({"autonomy": "guided", "brief_package": {"a": 1}}, True),
    ({"autonomy": " Autonomous "}, True),
    ({"autonomy": "unattended"}, True),
    ([1], False),
])
def test_mode_detection(tmp_path, cfg, expected):
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")
    assert pdc.is_autonomous_design_run(tmp_path) is expected


def test_missing_or_corrupt_config_is_interactive(tmp_path):
    assert pdc.is_autonomous_design_run(tmp_path) is False
    (tmp_path / "shipwright_run_config.json").write_text("{", encoding="utf-8")
    assert pdc.is_autonomous_design_run(tmp_path) is False


def test_findings_kinds():
    text = ('- reads "Thread bord"\n- button text shows "Previous thread"\n'
            "- picker at the 768px breakpoint\n- background color #0d9589\n"
            "- Design contradiction: a vs b\n")
    kinds = {f.kind for f in pdc.design_findings(text, {"s.html": SCREEN})}
    assert kinds == {"text_mismatch", "visible_vs_attribute", "breakpoint_mismatch",
                     "color_mismatch", "unresolved_contradiction"}


def test_covered_by_decision_and_harmless_additions():
    text = ('- reads "Thread bord"\n- Design decision: "Thread bord" -> "Thread board", screen wins\n'
            '- adds "Export CSV"\n- aria-label "Previous thread" is on the button\n- breakpoint 900px\n')
    assert pdc.design_findings(text, {"s.html": SCREEN}) == []


def test_section_line_parsers_and_marker():
    t = "- Design decision: x -> y, why\n- Design contradiction: a vs b; rule cannot decide\n"
    assert pdc.section_decisions(t) == ["x -> y, why"]
    assert pdc.section_contradictions(t)[0].endswith("rule cannot decide")
    assert pdc.design_findings(t, {}) == []


def test_design_problems_modes(tmp_path):
    planning = tmp_path / "p"
    (planning / "sections").mkdir(parents=True)
    scr = tmp_path / ".shipwright" / "designs" / "screens"
    scr.mkdir(parents=True)
    (scr / "s.html").write_text(SCREEN, encoding="utf-8")
    (tmp_path / ".shipwright" / "designs" / "visual-guidelines.md").write_text("#0d9488", encoding="utf-8")
    (planning / "sections" / "a.md").write_text(
        "## Design Reference\n- Screen mockup: .shipwright/designs/screens/s.html\n" '- reads "Thread bord"\n',
        encoding="utf-8")
    (planning / "sections" / "b.md").write_text("no ui here", encoding="utf-8")
    _cfg(tmp_path, autonomy="guided")
    problems, notes = pdc.design_problems(planning, tmp_path)
    assert problems == [] and len(notes) == 1
    _cfg(tmp_path, brief_package={"x": 1})
    problems, notes = pdc.design_problems(planning, tmp_path)
    assert len(problems) == 1 and notes == [] and "text_mismatch" in problems[0]


SCREEN_A = ('<html><body><p>Save &amp; close</p><p>Reply drafted</p><input placeholder="Search threads">'
            '<style>@media (min-width: 640px) and (max-width: 899px){.a{}}</style></body></html>')
SCREEN_B = ('<html><body><p>Reply posted</p><style>@media (max-width: 600px){.a{}}</style>'
            '<script>const t = "Thread archived";</script></body></html>')


def test_false_stop_regressions_from_review():
    text = ('- uses `ThreadBoard` and "reply-drafted" and "ThreadBoard" ids\n'
            '- the label reads "Save & close"\n- search input shows "Search threads"\n'
            '- the toast says "Reply posted" and later "Thread archived"\n'
            '- breakpoints at 640px, 899px and 600px\n- shows "Page 2 of 3"\n')
    screens = {"a.html": SCREEN_A + "<p>Page 1 of 3</p>", "b.html": SCREEN_B}
    assert pdc.design_findings(text, screens) == []


def test_layout_prose_with_px_is_not_a_breakpoint_claim():
    text = "- below the header a 320px sidebar; the sidebar collapses under 1200px max-width\n"
    assert pdc.design_findings(text, {"a.html": SCREEN_A}) == []


def test_external_stylesheet_disables_breakpoint_check():
    html = '<link rel="stylesheet" href="k.css"><style>@media (max-width: 900px){}</style>'
    assert pdc.design_findings("- the breakpoint is 768px\n", {"a.html": html}) == []


def test_extension_line_does_not_resolve_a_mismatch():
    text = '- reads "Thread bord"\n- Design extension: "Thread bord" - FR-01.01, not in s.html\n'
    assert [f.kind for f in pdc.design_findings(text, {"s.html": SCREEN})] == ["text_mismatch"]


def test_missing_referenced_screen_is_reported(tmp_path):
    planning = tmp_path / "p"
    (planning / "sections").mkdir(parents=True)
    (planning / "sections" / "a.md").write_text(
        "## Design Reference\n- Screen mockup: .shipwright/designs/screens/gone.html\n", encoding="utf-8")
    problems, _ = pdc.design_problems(planning, tmp_path, autonomous=True)
    assert problems == ["a: referenced screen not found: gone.html"]


def test_font_link_does_not_disable_breakpoint_check_and_innerhtml_is_known():
    html = ('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">'
            '<style>@media (max-width: 900px){}</style><p>Reply drafted</p>'
            "<script>el.innerHTML = '<p>Reply posted</p>';</script>")
    kinds = [f.kind for f in pdc.design_findings('- breakpoint 768px\n- says "Reply posted"\n', {"a.html": html})]
    assert kinds == ["breakpoint_mismatch"]
