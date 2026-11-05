"""In-process tests for lib/autonomous_rules.py and lib/phase_boundary_baseline.py (e2e run 22 rules)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from lib import autonomous_rules as ar
from lib import design_gate_html
from lib import phase_boundary_baseline as pbb

sys.path.append(str(Path(__file__).resolve().parent))
from _brief_dir_helpers import bp, build_package  # noqa: E402

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


EVIL = '<a href="https://evil.example/x">only in the editable uploads copy</a>'
KEPT = ["screens/01-board.html: approved package link https://www.reddit.com/r/x/comments/1",
        "screens/01-board.html: approved package link https://news.ycombinator.com/item?id=2"]


def _package(root: Path, *, record: bool = True) -> Path:
    """A verified package whose own mockup carries the two links; run_config records its hash."""
    bdir = build_package(root)
    (bdir / "mockups" / "sub").mkdir()
    (bdir / "mockups" / "sub" / "02-board.html").write_text(UPLOAD, encoding="utf-8")
    pkg = {"package_sha256": bp.package_sha256(bdir)} if record else {}
    _cfg(root, autonomy="autonomous", brief_dir="brief", brief_package=pkg)
    return bdir


def _designs(root: Path, screen: str, applied: bool = True) -> Path:
    designs = root / ".shipwright" / "designs"
    for d in ("screens", "uploads"):
        (designs / d).mkdir(parents=True, exist_ok=True)
    (designs / "uploads" / "01-board.html").write_text(UPLOAD + EVIL, encoding="utf-8")  # never the approved set
    (designs / "screens" / "01-board.html").write_text(screen, encoding="utf-8")
    if applied:
        (designs / "brief-package-applied.json").write_text("{}", encoding="utf-8")
    return designs


SCREEN = UPLOAD + EVIL + '<script src="https://cdn.example/a.js"></script>'
FILES = ["screens/01-board.html", "screens/missing.html"]


def test_a_verified_package_keeps_exactly_its_own_links(tmp_path):
    _package(tmp_path)
    _designs(tmp_path, SCREEN)
    problems, kept, unverified = ar.standalone_findings(tmp_path, FILES)
    assert sorted(kept) == sorted(KEPT) and unverified == ""
    assert problems == ["screens/01-board.html: external reference https://evil.example/x",
                        "screens/01-board.html: external reference https://cdn.example/a.js"]


def test_a_changed_package_keeps_nothing_and_says_why(tmp_path):
    bdir = _package(tmp_path)
    _designs(tmp_path, SCREEN)
    (bdir / "mockups" / "sub" / "02-board.html").write_text(UPLOAD + EVIL, encoding="utf-8")  # after approval
    problems, kept, unverified = ar.standalone_findings(tmp_path, FILES)
    assert kept == [] and len(problems) == 4 and "hash_mismatch" in unverified


@pytest.mark.parametrize("cfg,applied", [
    ({"autonomy": "guided"}, True),  # interactive: unchanged, the links fail as before
    ({"autonomy": "autonomous"}, False),  # no applied package: nothing is "approved"
])
def test_no_approved_links_outside_an_autonomous_package_run(tmp_path, cfg, applied):
    _package(tmp_path)
    _cfg(tmp_path, brief_dir="brief", **cfg)
    _designs(tmp_path, SCREEN, applied)
    assert ar.standalone_findings(tmp_path, FILES)[1:] == ([], "")


def test_without_a_recorded_hash_nothing_is_trusted(tmp_path, monkeypatch):
    _package(tmp_path, record=False)
    _designs(tmp_path, SCREEN)
    problems, kept, unverified = ar.standalone_findings(tmp_path, FILES)
    assert kept == [] and "no brief package directory and hash" in unverified
    _package(tmp_path / "p2")
    monkeypatch.setattr(ar._brief_package, "verify_package", lambda *_a, **_k: (_ for _ in ()).throw(OSError("gone")))
    assert ar.verified_package_mockups(tmp_path / "p2") == (None, "the brief package cannot be verified: gone")


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
    ("npm install --ignore-scripts", True),
    ("npm ci --ignore-scripts", True),
    ("pnpm install --ignore-scripts --frozen-lockfile", True),
    ("npm i -D --ignore-scripts @playwright/test", True),
    ("npm install", False),  # lifecycle scripts would run
    ("npm ci", False),
    ("npm i -D @playwright/test", False),
    ("npm i -D --ignore-scripts @playwright/test@1.59.1", False),  # a version spec changes the declared range
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
    assert ar.dev_tooling_verdict("npm install --ignore-scripts", tmp_path)[0] is False  # no package.json
    _pkg(tmp_path, {"vitest": "1"})
    assert ar.dev_tooling_verdict("npx playwright install chromium", tmp_path)[0] is False
    (tmp_path / "package.json").write_text("not json", encoding="utf-8")
    assert ar.dev_tooling_verdict("npm install --ignore-scripts", tmp_path)[0] is True  # installs the manifest


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


def test_loaded_top_level_it_still_verifies_through_the_private_package(tmp_path, monkeypatch):
    """check-design-gates.py imports the module by name (``lib`` on sys.path): the relative imports
    fail there, and brief_package (relative imports of its own) comes through shared_lib_loader."""
    import importlib.util
    lib = Path(ar.__file__).resolve().parent
    scripts = lib.parent

    def _is_scripts(entry: str) -> bool:
        try:
            return bool(entry) and Path(entry).resolve() == scripts
        except OSError:
            return False

    monkeypatch.setattr(sys, "path", [str(lib)] + [p for p in sys.path if not _is_scripts(p)])
    spec = importlib.util.spec_from_file_location("autonomous_rules_toplevel", lib / "autonomous_rules.py")
    mod = importlib.util.module_from_spec(spec)
    before = list(sys.path)
    spec.loader.exec_module(mod)  # _private adds shared/scripts for the loader, then removes it again
    assert sys.path == before and not any(_is_scripts(p) for p in sys.path)
    assert mod._brief_package.__name__ != "brief_package"  # never bound top-level: it would not import
    _package(tmp_path)
    mockups, why = mod.verified_package_mockups(tmp_path)
    assert why == "" and mockups == (tmp_path / "brief" / "mockups").resolve()
