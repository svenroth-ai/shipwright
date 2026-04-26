"""Verify route_crawler surfaces useful diagnostic on Playwright test failure.

Bug: when `npx playwright test` fails, the returned summary used to be
`{status: "no_output", stderr: ""}` because Playwright's stderr is empty —
the test report goes to `test-results/<spec>/error-context.md` and
`playwright-report/`. This left the user with no actionable info.

Fix: on non-success, glob `<run_cwd>/test-results/` for the latest
error-context.md and surface its tail.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import route_crawler  # noqa: E402


def test_no_output_includes_error_context_tail(tmp_path, monkeypatch):
    """When routes.json is missing AND test-results has an error-context, surface it."""

    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(route_crawler.subprocess, "run", fake_run)

    # Plant a Playwright-style error-context.md
    test_results = tmp_path / "test-results" / "_shipwright-adopt-crawler-shipwright-adopt-route-crawler"
    test_results.mkdir(parents=True)
    err_path = test_results / "error-context.md"
    err_path.write_text(
        "# Test info\n\n- Name: shipwright-adopt route crawler\n- Expected: success\n\n"
        "## Page snapshot\n\n```yaml\n- page goto failed: net::ERR_CONNECTION_REFUSED\n```\n",
        encoding="utf-8",
    )

    output = tmp_path / ".shipwright" / "adopt" / "routes.json"
    screenshots = tmp_path / ".shipwright" / "adopt" / "screenshots"

    summary = route_crawler.run_crawl(
        tmp_path,
        base_url="http://localhost:5173",
        output=output,
        screenshots_dir=screenshots,
        max_depth=1,
        max_pages=10,
        auth_token=None,
    )

    assert summary["status"] == "no_output"
    # The tail of error-context.md should be in the summary
    assert "error_context" in summary, f"expected error_context field in {summary}"
    assert "ERR_CONNECTION_REFUSED" in summary["error_context"]


def test_no_output_handles_missing_test_results_dir(tmp_path, monkeypatch):
    """If test-results doesn't exist (e.g. crash before tests started),
    don't error — just include an empty error_context."""

    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(route_crawler.subprocess, "run", fake_run)
    output = tmp_path / ".shipwright" / "adopt" / "routes.json"
    screenshots = tmp_path / ".shipwright" / "adopt" / "screenshots"

    summary = route_crawler.run_crawl(
        tmp_path,
        base_url="http://localhost:5173",
        output=output,
        screenshots_dir=screenshots,
        max_depth=1,
        max_pages=10,
        auth_token=None,
    )

    assert summary["status"] == "no_output"
    # Field present even if empty
    assert summary.get("error_context", "") == ""


def test_error_context_uses_config_dir_when_set(tmp_path, monkeypatch):
    """For multi-service runs (config_dir=client/), error-context lives
    under <client>/test-results/, not <project_root>/test-results/."""

    def fake_run(cmd, **kwargs):
        class _R:
            returncode = 1
            stdout = ""
            stderr = ""

        return _R()

    monkeypatch.setattr(route_crawler.subprocess, "run", fake_run)

    client = tmp_path / "client"
    client.mkdir()
    test_results = client / "test-results" / "anything"
    test_results.mkdir(parents=True)
    (test_results / "error-context.md").write_text(
        "FAILURE_MARKER_FROM_CLIENT_TEST_RESULTS", encoding="utf-8"
    )

    output = tmp_path / ".shipwright" / "adopt" / "routes.json"
    screenshots = tmp_path / ".shipwright" / "adopt" / "screenshots"

    summary = route_crawler.run_crawl(
        tmp_path,
        base_url="http://localhost:5173",
        output=output,
        screenshots_dir=screenshots,
        max_depth=1,
        max_pages=10,
        auth_token=None,
        config_dir=client,
    )

    assert "FAILURE_MARKER_FROM_CLIENT_TEST_RESULTS" in summary.get("error_context", "")
