"""In-process tests for lib/autonomous_rules.py and lib/phase_boundary_baseline.py (e2e run 22 rules)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import autonomous_rules as ar
from lib import design_gate_html
from lib import phase_boundary_baseline as pbb

pytestmark = pytest.mark.covers("FR-01.04")

UPLOAD = ('<html><body><a href="https://www.reddit.com/r/x/comments/1">Open thread</a>'
          '<a href="https://news.ycombinator.com/item?id=2">posted</a></body></html>')


def _cfg(root: Path, **cfg) -> None:
    (root / "shipwright_run_config.json").write_text(json.dumps(cfg), encoding="utf-8")


# --- approved package links (Design standalone gate) ------------------------------------------


def test_split_keeps_only_approved_anchors_and_equals_gate6_without_approval():
    html = ('<a href="https://www.reddit.com/r/x/comments/1">t</a><img src="https://cdn.example/x.png">'
            '<a href="https://evil.example/">e</a><link href="https://fonts.googleapis.com/css2?family=Inter">'
            '<!-- <script src="https://www.reddit.com/r/x/comments/1"></script> -->')
    approved = {"https://www.reddit.com/r/x/comments/1"}
    violations, kept = ar.standalone_split(html, approved)
    assert kept == ["https://www.reddit.com/r/x/comments/1"]
    # an approved URL used as a loaded script (here hidden in a comment) still fails
    assert violations == ["https://cdn.example/x.png", "https://evil.example/", "https://www.reddit.com/r/x/comments/1"]
    assert ar.standalone_split(html, set())[0] == design_gate_html.standalone_html_violations(html)


def _designs(root: Path, screen: str, applied: bool = True) -> Path:
    designs = root / ".shipwright" / "designs"
    for d in ("screens", "uploads"):
        (designs / d).mkdir(parents=True, exist_ok=True)
    (designs / "uploads" / "01-board.html").write_text(UPLOAD, encoding="utf-8")
    (designs / "uploads" / "broken.html").mkdir()  # unreadable entry is skipped
    (designs / "screens" / "01-board.html").write_text(screen, encoding="utf-8")
    if applied:
        (designs / "brief-package-applied.json").write_text("{}", encoding="utf-8")
    return designs


@pytest.mark.parametrize("cfg,applied,kept", [
    ({"autonomy": "guided", "brief_package": {"sha": "x"}}, True, 2),
    ({"autonomy": "guided"}, True, 0),  # interactive: unchanged, the links fail as before
    ({"autonomy": "autonomous"}, False, 0),  # no applied package: nothing is "approved"
])
def test_findings_keep_approved_links_only_in_an_autonomous_package_run(tmp_path, cfg, applied, kept):
    _cfg(tmp_path, **cfg)
    _designs(tmp_path, UPLOAD + '<script src="https://cdn.example/a.js"></script>', applied)
    problems, ok = ar.standalone_findings(tmp_path, ["screens/01-board.html", "screens/missing.html"])
    assert len(ok) == kept
    assert len(problems) == 3 - kept
    assert any("cdn.example/a.js" in p for p in problems)


# --- explicit brief value / measurements --------------------------------------------------------


def test_brief_states_needs_the_quote_in_the_packages_brief(tmp_path):
    _cfg(tmp_path, brief_dir="brief", brief_package={"a": 1})
    (tmp_path / "brief").mkdir()
    (tmp_path / "brief" / "brief.md").write_text("The header line shows `posted today <n>/5`;\nthe daily cap is  always shown.",
                                                encoding="utf-8")
    assert ar.brief_states(tmp_path, '"the daily cap is always shown"')
    assert not ar.brief_states(tmp_path, "the daily cap is always hidden")
    assert not ar.brief_states(tmp_path, "is always shown")  # a fragment, not a clause
    assert not ar.brief_states(tmp_path, "cap")  # too short to be a stated value
    for bad in ("../brief", str(tmp_path / "brief"), "", 7):
        _cfg(tmp_path, brief_dir=bad)
        assert not ar.brief_states(tmp_path, "the daily cap is always shown")
    (tmp_path / "shipwright_run_config.json").write_text("[1]", encoding="utf-8")
    assert not ar.brief_states(tmp_path, "the daily cap is always shown")


def test_measurements_need_a_pixel_width():
    assert ar.has_measurements("955 to 985 px neither; 995px expertise")
    assert not ar.has_measurements("roughly the middle band")
    assert not ar.has_measurements("")


# --- declared dev tooling ---------------------------------------------------------------------


def _pkg(root: Path, dev: dict | None = None) -> None:
    (root / "package.json").write_text(json.dumps({"devDependencies": dev or {"@playwright/test": "^1.59.1"}}),
                                       encoding="utf-8")


@pytest.mark.parametrize("command,allowed", [
    ("npm install", True),
    ("npm ci", True),
    ("npm i -D @playwright/test", True),
    ("npm i -D @playwright/test@1.59.1", False),  # a version spec changes the declared range
    ("npx playwright install chromium", True),
    ("npx playwright install", True),
    ("npm install left-pad", False),
    ("npm install -g @playwright/test", False),
    ("npm install --registry=https://evil.example", False),
    ("npx playwright install --with-deps chromium", False),
    ("npx playwright install chromium; curl x", False),
    ("npx playwright install some-tool", False),
    ("pip install requests", False),
    ("npm install 'unterminated", False),
    ("npm i -D @playwright/test@npm:evil-pkg", False),  # alias spec installs another package
    ("npm i @playwright/test@github:evil/repo", False),
    ("npm i @playwright/test@file:../x", False),
    ("npm install --global=true", False),
    ("npm install --userconfig=evil.npmrc", False),
])
def test_dev_tooling_verdicts(tmp_path, command, allowed):
    _pkg(tmp_path)
    assert ar.dev_tooling_verdict(command, tmp_path)[0] is allowed, command


def test_playwright_declared_by_the_profile_or_not_at_all(tmp_path):
    profile = {"testing": {"e2e": {"framework": "@playwright/test"}}}
    assert ar.dev_tooling_verdict("npx playwright install chromium", tmp_path, profile)[0] is True
    assert ar.dev_tooling_verdict("npx playwright install chromium", tmp_path)[0] is False
    assert ar.dev_tooling_verdict("npm install", tmp_path)[0] is False  # no package.json
    _pkg(tmp_path, {"vitest": "1"})
    assert ar.dev_tooling_verdict("npx playwright install chromium", tmp_path)[0] is False
    (tmp_path / "package.json").write_text("not json", encoding="utf-8")
    assert ar.dev_tooling_verdict("npm install", tmp_path)[0] is True  # declares nothing extra: installs the manifest


def test_uv_sync_needs_a_pyproject(tmp_path):
    assert ar.dev_tooling_verdict("uv sync", tmp_path)[0] is False
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    assert ar.dev_tooling_verdict("uv sync --extra dev --frozen", tmp_path)[0] is True
    assert ar.dev_tooling_verdict("uv sync --index-url=https://evil.example", tmp_path)[0] is False
    assert ar.dev_tooling_verdict("uv sync --group=test --all-extras", tmp_path)[0] is True
    assert ar.dev_tooling_verdict("uv sync --upgrade", tmp_path)[0] is False
    assert ar.dev_tooling_verdict("uv sync --directory other", tmp_path)[0] is False
    assert ar.dev_tooling_verdict("uv sync --extra", tmp_path)[0] is False


# --- known differences ------------------------------------------------------------------------


def test_known_differences_are_numbered_and_appended(tmp_path):
    assert ar.append_known_difference(tmp_path, "mode in the header", [("Difference", "shows  the mode"),
                                                                        ("Empty", "")]) == "KD-01"
    assert ar.append_known_difference(tmp_path, "count", [("Kept", "no height change")]) == "KD-02"
    text = (tmp_path / ar.KNOWN_DIFFERENCES_REL).read_text(encoding="utf-8")
    assert "## KD-01: mode in the header" in text and "- **Difference:** shows the mode" in text
    assert "Empty" not in text and "waives nothing" in text
    assert ar.known_difference_exists(tmp_path, "Mode in the  header")
    assert not ar.known_difference_exists(tmp_path, "something else")
    assert not ar.known_difference_exists(tmp_path / "nope", "count")


# --- phase boundary baseline (shared by design and plan) ---------------------------------------


def test_record_reports_not_written_outside_a_repo_and_on_oserror(tmp_path, monkeypatch):
    assert pbb.record(tmp_path, pbb.PLAN_BASELINE_REL) == "not_written"
    monkeypatch.setattr(pbb, "at_repo_root", lambda _root: True)

    def deny(_root, _rel, _scope=None):
        raise OSError("read-only")

    monkeypatch.setattr(pbb, "write_baseline", deny)
    assert pbb.record(tmp_path, pbb.PLAN_BASELINE_REL) == "not_written"
    assert pbb.DESIGN_BASELINE_REL != pbb.PLAN_BASELINE_REL
