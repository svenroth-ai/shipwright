"""Verify the crawler.ts.template wait-strategy is configurable + non-hanging.

Regression: `await page.waitForLoadState('networkidle', { timeout: 10_000 })`
never resolves on polling-heavy SPAs (constant 1s polling). With 50 pages the
180s test timeout fires after just ~1 page processed, killing the entire crawl.

Fix:
  - Default strategy is 'load' with a short (3s) timeout
  - SHIPWRIGHT_CRAWL_WAIT_STRATEGY env can override (load|networkidle|domcontentloaded)
  - Always followed by a small fixed settle (waitForTimeout(500))
"""

from __future__ import annotations

from pathlib import Path

TEMPLATE = (
    Path(__file__).resolve().parent.parent / "templates" / "crawler.ts.template"
)


def _read_template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_template_does_not_use_naked_networkidle_default():
    """The old hanging line must be gone — no `'networkidle', { timeout: 10_000 }`
    pattern as the unconditional default."""
    body = _read_template()
    # `'networkidle'` may appear as a strategy option; what we ban is the
    # specific old hanging call site.
    assert "waitForLoadState('networkidle', { timeout: 10_000 })" not in body, (
        "naked networkidle wait still present in template"
    )


def test_template_reads_wait_strategy_env():
    body = _read_template()
    assert "SHIPWRIGHT_CRAWL_WAIT_STRATEGY" in body


def test_template_default_is_load_strategy():
    body = _read_template()
    # The fallback when env is unset should be 'load'
    assert "'load'" in body


def test_template_includes_settle_after_wait():
    body = _read_template()
    # Either waitForTimeout(500) or similar small fixed settle
    assert "waitForTimeout(500)" in body or "waitForTimeout(500 " in body
