"""Verify the crawler.ts.template is robust against test-timeout data loss
and silent screenshot failures (sub-iterate B).

Background: the original template wrote `routes.json` only at the end. On
test timeout (180s default) the BFS loop is mid-iteration and the final
fs.writeFileSync never reached — all crawled data lost. Screenshots
similarly failed silently with .catch(() => {}) so routes.json claimed
files existed that didn't.
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parent.parent / "templates" / "crawler.ts.template"
)


def _read_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


# 2.1 — incremental writes / try-finally
# ---------------------------------------------------------------------------

def test_template_uses_try_finally_around_bfs_loop():
    """End-of-test fs.writeFileSync alone is not enough — must be in a
    finally block so a test-timeout still flushes partial results."""
    body = _read_template()
    assert "try {" in body or "try{" in body, "no try block in template"
    assert "finally" in body, "no finally block — partial results would be lost on timeout"


def test_template_writes_routes_inside_loop_or_finally():
    """Either incremental per-page writes OR a finally-block flush. Both
    are acceptable; both protect against the timeout scenario."""
    body = _read_template()
    # Pattern: writeFileSync should appear inside a finally OR inside the BFS while loop
    # We can't easily AST-parse — assert the writeFileSync is not the only
    # last statement, AND the finally block contains writeFileSync.
    finally_idx = body.find("finally")
    write_idx = body.find("fs.writeFileSync(OUT_JSON")
    assert finally_idx != -1
    assert write_idx > finally_idx, (
        "fs.writeFileSync should be inside the finally block (after the `finally` keyword)"
    )


# 2.2 — screenshot error capture
# ---------------------------------------------------------------------------

def test_template_captures_screenshot_error_into_entry():
    """When page.screenshot fails, the error must be recorded in the route
    entry as `screenshot_error`, NOT silently swallowed."""
    body = _read_template()
    assert "screenshot_error" in body, (
        "screenshot_error field missing — failures still silently lost"
    )


def test_template_logs_screenshot_error_to_stderr():
    """In addition to the entry field, the error should hit stderr so the
    Python wrapper sees it in subprocess output."""
    body = _read_template()
    # Either console.error or process.stderr.write
    assert "console.error" in body or "process.stderr" in body, (
        "no stderr-side logging of screenshot errors"
    )


def test_template_screenshot_no_silent_swallow():
    """Banned pattern: bare `.catch(() => { /* ignore */ })` on screenshot.
    The whole point of 2.2 is that we stop silently lying."""
    body = _read_template()
    # The OLD bug pattern, anchored to the screenshot call site
    assert "page.screenshot({ path: screenshotPath, fullPage: false }).catch(() => { /* ignore */ })" not in body
