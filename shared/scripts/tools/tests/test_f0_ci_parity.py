"""AC2 parity guard — the F0 runner and ci.yml must select the SAME test units.

CI deliberately stays SERIAL (it is the independent cross-check that would catch a
parallel-only false green — see references/F0.md). That only works while both sides
run the same units. This guard fails if ci.yml stops using the selection rule the
runner re-implements, forcing a conscious re-sync instead of silent drift.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

from scripts.tools.suite_units import (
    INTEGRATION_DIR,
    PYTHON_VERSION,
    SHARED_TEST_DIRS,
    discover_units,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_CI = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

pytestmark = pytest.mark.skipif(not _CI.is_file(), reason="ci.yml not present (not the monorepo)")


@pytest.fixture(scope="module")
def ci_text() -> str:
    return _CI.read_text(encoding="utf-8")


def test_ci_still_loops_plugins_on_pyproject_plus_tests(ci_text):
    """The runner's plugin rule: plugins/*/ having pyproject.toml AND tests/."""
    assert "for plugin in plugins/*/" in ci_text
    assert '[ -f "$plugin/pyproject.toml" ]' in ci_text
    assert '[ -d "$plugin/tests" ]' in ci_text


def test_ci_still_runs_the_same_shared_dirs(ci_text):
    """Pin the EXECUTABLE line, not the file text: ci.yml also names these dirs in long
    comments, so a substring-anywhere check would still pass if the loop were deleted."""
    assert f"for dir in {' '.join(SHARED_TEST_DIRS)}" in ci_text, \
        "ci.yml no longer loops over exactly the shared test dirs — F0/CI selection drifted"


def test_ci_still_runs_integration_tests(ci_text):
    assert f"pytest {INTEGRATION_DIR}/" in ci_text, \
        "ci.yml no longer runs the integration-tests step — F0/CI selection drifted"


def test_ci_keeps_the_shared_marker_expression(ci_text):
    """Same selection on both sides (AC3) — CI restates `not slow` because a CLI
    -m replaces the pyproject default."""
    assert 'not slow and not cross_plugin' in ci_text


def test_ci_stays_SERIAL(ci_text):
    """The load-bearing guard, not a style rule.

    F0's honest claim is that it only removes false STOPs — it does NOT prove serial
    equivalence for units that PASSED. The one thing that would catch a parallel-only
    false green is CI running the same units SERIALLY. Parallelising ci.yml would delete
    that cross-check while every other test in this repo stayed green. So: no xdist in
    CI's test steps, enforced.
    """
    for forbidden in ("--numprocesses", "pytest-xdist", "-n auto", "-p xdist"):
        assert forbidden not in ci_text, (
            f"ci.yml uses {forbidden!r}: CI must stay SERIAL — it is the independent "
            "cross-check for a parallel-only false green (see references/F0.md)."
        )


def _ci_surfaces() -> list[Path]:
    """Every file that can run this repo's Python in CI. `*.y*ml` because GitHub
    accepts both spellings, and composite actions because they are CI too."""
    return sorted([*(_REPO_ROOT / ".github" / "workflows").glob("*.y*ml"),
                   *(_REPO_ROOT / ".github" / "actions").glob("*/action.y*ml")])


def _executable(text: str) -> str:
    """Workflow text with comments removed — a DECLARATION must be live to count.

    Raised by external review: `# uv python install 3.11` sitting above an active
    unpinned `uv run` satisfied both guards, so commenting out CI's pin passed the very
    tests that exist to catch it. `#` is a comment in YAML and in shell alike when it
    starts a line or follows whitespace.

    Used ONLY for "does this surface DECLARE the pin". The opposite question — "does it
    RUN Python" — deliberately reads the RAW text, because each direction has to fail
    safe: over-detecting a run demands a declaration (loud), while under-detecting one
    would excuse a surface from declaring anything (quiet).
    """
    return "\n".join(re.sub(r"(?:(?<=\s)|^)#.*$", "", ln) for ln in text.splitlines())


def test_every_ci_surface_that_runs_python_declares_the_interpreter():
    """Absence must not read as agreement — raised by external review (GPT).

    The sibling test compares the versions that ARE declared, so it is blind to a
    surface that runs this repo's Python and declares nothing: that one resolves an
    ambient interpreter, which is precisely the defect this run closes, relocated from
    F0 into CI.

    Scope is `uv run` / `pytest`, i.e. executing THIS repo's code. A `uvx <tool>` call
    is deliberately exempt: it runs a pinned third-party tool whose own interpreter
    never judges the repo's behaviour (`.github/actions/diff-coverage-gate/action.yml`
    runs `uvx diff-cover` and is the current, intended example). Stating the exemption
    beats a silent skip — a guard that goes quiet is how this defect survived.
    """
    offenders = []
    for wf in _ci_surfaces():
        raw = wf.read_text(encoding="utf-8")
        # RAW to detect running Python (over-detecting only demands a declaration);
        # comment-stripped to detect the declaration (a commented pin is not a pin).
        if re.search(r"\buv run\b|\bpytest\b", raw) and "uv python install" not in _executable(raw):
            offenders.append(wf.name)
    assert not offenders, (
        f"{offenders} run this repo's Python but declare no interpreter, so CI resolves "
        f"an ambient one while F0 is pinned to {PYTHON_VERSION} — the same F0/CI split "
        "this guard exists to prevent, with the two sides swapped")


def test_runner_pins_the_interpreter_every_workflow_installs():
    """AC5 — the axis this guard was MISSING, and the reason the defect could exist.

    The four guards above pin WHICH units run and that CI stays serial; none pinned
    the INTERPRETER. Measured on `main` @ 6d2b2013: F0 ran the plugin units on
    3.13.13/3.12.13 while every workflow ran 3.11.15, so F0 could green a branch CI
    then rejected — with all four parity tests passing. Asserted across every CI
    surface, not just ci.yml: one interpreter fact for the repo, one owner.

    The token is captured WHOLE (`\\S+`) rather than matched as `\\d+\\.\\d+`, because a
    narrow pattern does not fail on a form it cannot parse — it silently skips it, and
    the other workflows keep the result non-empty. A quoted `"3.12"` or a
    `${{ matrix.python }}` would then read as full parity. A guard whose failure mode
    is going quiet is the exact shape that let this defect live behind four green tests.
    """
    found = {}
    for wf in _ci_surfaces():
        # Comment-stripped: a commented-out install must not read as a live pin.
        for token in re.findall(r"uv python install +(\S+)", _executable(wf.read_text(encoding="utf-8"))):
            found.setdefault(token, []).append(wf.name)
    assert found, "no CI surface installs an interpreter any more — F0/CI parity is unguarded"
    # `3.11` or any `3.11.x`: the patch level floats on BOTH sides by design (see
    # PYTHON_VERSION). Anything else - another minor, a quoted literal, an expression -
    # is a disagreement or an unparseable pin, and both must be loud.
    bad = {t: sorted(w) for t, w in found.items()
           if t != PYTHON_VERSION and not t.startswith(f"{PYTHON_VERSION}.")}
    assert not bad, (
        f"the F0 runner pins Python {PYTHON_VERSION} but CI installs {bad} — F0 would "
        "certify a branch on one interpreter while CI judges it on another (an "
        "unparseable token here is a disagreement too: it cannot be shown to agree)")


def test_every_tracked_version_file_agrees_with_the_runner_pin():
    """AC6 — 15 copies of one fact must not become 15 facts.

    A `.python-version` disagreeing with the argv pin is worse than none: `uv run`
    inside that directory would resolve one interpreter while F0 forces another.
    """
    root = _REPO_ROOT / ".python-version"
    # Asserted, not filtered: an `if is_file()` skip would let the ROOT file be deleted
    # while the 14 plugin files kept the check non-empty and green — AC3's guarantee
    # would then be exactly as deletable as AC4's was before this run.
    assert root.is_file(), (
        "the repo-root .python-version is gone: every bare root-level `uv run` (hooks, "
        f"finalization tools, `uv sync`) is back on ambient state instead of {PYTHON_VERSION}")
    files = [root, *sorted(_REPO_ROOT.glob("plugins/*/.python-version"))]
    disagreeing = {str(f.relative_to(_REPO_ROOT)): v for f in files
                   if (v := f.read_text(encoding="utf-8").strip()) != PYTHON_VERSION}
    assert not disagreeing, f"version files disagree with the pin {PYTHON_VERSION}: {disagreeing}"


def test_every_plugin_ci_runs_carries_its_own_version_file():
    """Reverse drift direction: a NEW plugin must not silently reopen the gap.

    A root `.python-version` does not reach a plugin directory — each carries its own
    `pyproject.toml`, so it is its own uv project and discovery stops there (measured:
    with `3.11` at the root, `plugins/shipwright-adopt` still built 3.12.13). So the
    hand-run `cd plugins/<name> && uv run pytest tests/` that CLAUDE.md documents needs
    a file per plugin, or it resolves whatever the machine happens to offer.
    """
    missing = sorted(
        p.name for p in (_REPO_ROOT / "plugins").iterdir()
        if (p / "pyproject.toml").is_file() and (p / "tests").is_dir()
        and not (p / ".python-version").is_file())
    assert not missing, (
        f"plugins without a .python-version: {missing} — `cd plugins/<name> && uv run "
        f"pytest tests/` there resolves an ambient interpreter, not the {PYTHON_VERSION} "
        "CI judges the push with")


def test_runner_discovers_every_plugin_ci_would_run():
    """Forward direction: no plugin with tests is missing from the runner's units."""
    discovered = {u.id for u in discover_units(_REPO_ROOT)}
    expected = {
        p.name for p in (_REPO_ROOT / "plugins").iterdir()
        if (p / "pyproject.toml").is_file() and (p / "tests").is_dir()
    }
    assert expected <= discovered
    assert expected, "no plugin units discovered — the glob is broken"
