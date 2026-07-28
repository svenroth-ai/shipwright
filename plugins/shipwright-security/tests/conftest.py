"""Test fixtures for shipwright-security."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
PLUGIN_ROOT = Path(__file__).parent.parent


@pytest.fixture(autouse=True)
def _no_source_tree_pollution():
    """Fail any test that writes ``.shipwright/`` into the plugin source tree.

    Several entry points take a ``--project-root`` that DEFAULTS to ``"."`` and
    then write under it — ``generate_security_report.main()`` mirrors findings
    into ``<project_root>/.shipwright/triage.jsonl``. The plugin's own pytest
    session runs with the CWD set to the plugin directory, so a test that omits
    the flag silently writes into the repository instead of a tmp_path. That is
    how ``plugins/shipwright-security/.shipwright/triage.jsonl`` kept
    reappearing as an untracked file.

    Complements — does not replace — the ``pytest_sessionfinish`` guard below.
    This one names the OFFENDING TEST and covers the whole ``.shipwright/`` tree;
    that one is the ordering-proof session backstop over three specific paths.
    Neither is redundant: a leak into ``.shipwright/securityreports/`` (which
    ``run_scan_and_report.py`` writes) is invisible to the path list, and a leak
    created outside any test's teardown window is invisible to this fixture.

    **Deliberately does not delete.** An earlier version called
    ``shutil.rmtree`` here, which made the session hook below dead code — proven
    by reintroducing a leak: only this fixture ever fired. It also destroyed the
    evidence, against the explicit reasoning of
    iterate-2026-07-27-security-test-triage-leak: the leaked file holds fixtures
    that read as real security findings, and a stray ``.lock`` is the shape that
    later produces merge conflicts, so a developer needs to SEE it. Cascading is
    prevented by the ``existed`` snapshot, not by cleaning up — a later test sees
    the directory as pre-existing and stays silent.
    """
    marker = PLUGIN_ROOT / ".shipwright"
    existed = marker.exists()
    yield
    if marker.exists() and not existed:
        leaked = sorted(str(p.relative_to(PLUGIN_ROOT)) for p in marker.rglob("*")
                        if p.is_file())
        pytest.fail(
            "this test wrote into the plugin source tree: "
            f"{', '.join(leaked) or '.shipwright/'}. An entry point whose "
            "--project-root defaults to '.' was invoked without one, so it "
            "targeted the CWD (the plugin dir) instead of a tmp_path. Pass "
            "--project-root str(tmp_path).",
            pytrace=False,
        )


@pytest.fixture
def sample_aikido_response() -> list[dict]:
    """Load sample Aikido API response."""
    return json.loads((FIXTURES_DIR / "sample_aikido_response.json").read_text())


@pytest.fixture
def sample_fixable_findings() -> dict:
    """Load sample findings with expected classifications."""
    return json.loads((FIXTURES_DIR / "sample_fixable_findings.json").read_text())


@pytest.fixture
def sample_semgrep_output() -> dict:
    """Load sample Semgrep JSON output."""
    return json.loads((FIXTURES_DIR / "sample_semgrep_output.json").read_text())


@pytest.fixture
def sample_trivy_output() -> dict:
    """Load sample Trivy JSON output."""
    return json.loads((FIXTURES_DIR / "sample_trivy_output.json").read_text())


@pytest.fixture
def sample_gitleaks_output() -> list:
    """Load sample Gitleaks JSON output."""
    return json.loads((FIXTURES_DIR / "sample_gitleaks_output.json").read_text())


# ---------------------------------------------------------------------------
# Leak guard — runs AFTER the whole session, not as a test
# ---------------------------------------------------------------------------

PLUGIN_ROOT = Path(__file__).resolve().parent.parent

# Written by the triage store. None is gitignored under the plugin, so a later
# `git add -A` commits them: fixture findings that read as real security
# findings, plus a `.lock` of exactly the shape that later causes merge
# conflicts. Happened twice in one session (PRs #446, #461).
_LEAK_PATHS = (
    PLUGIN_ROOT / ".shipwright" / "triage.jsonl",
    PLUGIN_ROOT / ".shipwright" / "triage.jsonl.lock",
    PLUGIN_ROOT / ".shipwright" / "triage.outbox.jsonl",
)


def pytest_sessionfinish(session, exitstatus):
    """Fail the session if any test wrote a triage store into the plugin dir.

    A HOOK, not a test, and deliberately so: the first attempt at this guard
    was an ordinary test module, which pytest ran alphabetically BEFORE the
    module that leaks — it passed while the leak was reintroduced, proving
    nothing. Only `sessionfinish` sees the end state regardless of ordering.

    Cause when it fires: a test drives a producer whose `--project-root`
    defaults to `"."`. Pass `tmp_path`; do not gitignore the symptom.

    Complements the ``_no_source_tree_pollution`` fixture above, which names the
    offending test and watches the whole ``.shipwright/`` tree. This hook is the
    ordering-proof net: it also sees a leak created outside any test's teardown
    window, which a per-test fixture cannot. Keep both.
    """
    leaked = [p for p in _LEAK_PATHS if p.exists()]
    if not leaked:
        return
    names = ", ".join(str(p.relative_to(PLUGIN_ROOT)) for p in leaked)
    print(
        "\n[leak-guard] the test suite wrote a triage store into the plugin "
        f"directory: {names}\n"
        "[leak-guard] a test is driving a producer without an isolated "
        "--project-root (its default is '.'). Pass tmp_path."
    )
    session.exitstatus = 1
