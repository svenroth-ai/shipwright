"""Adopt's Layer-3 review must be runnable and self-diagnosing (#547).

Reported against a real repository: the review failed with "openai package not
installed" because the plugin never declared ``openai`` (mocked-HTTP tests
cannot see this - the mock replaces the very import that was missing), the
artifact then said only ``_no feedback_``, and ``validate_adoption`` still
returned ``ok: true`` with no warning.
"""

from __future__ import annotations

import importlib.util
import sys
import tomllib
from pathlib import Path

import pytest

import checks.validate_adoption as validate_adoption

_PLUGIN = Path(__file__).resolve().parents[1]
_LIB = _PLUGIN / "scripts" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import review_runner  # noqa: E402

_SNAPSHOT = {"profile": {"matched": "python"}, "features": [], "stack": {}}


def _declared() -> set[str]:
    deps = tomllib.loads((_PLUGIN / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    return {d.split(">")[0].split("=")[0].split("<")[0].strip().lower() for d in deps}


@pytest.mark.covers("FR-01.13/AC07")
@pytest.mark.parametrize("package", ["openai", "jsonschema"])
def test_review_dependencies_are_declared_and_importable(package):
    """Declared AND resolvable in the plugin's own environment - the
    environment `uv run` builds, not whatever the developer machine has."""
    assert package in _declared()
    assert importlib.util.find_spec(package) is not None, (
        f"{package} is declared but not installed - run `uv sync` in plugins/shipwright-adopt"
    )


def _fake_llm_review(monkeypatch, result):
    fake = type(sys)("llm_review")
    fake.run_review = lambda *_a, **_kw: result  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llm_review", fake)


def _all_legs_failed() -> dict:
    return {
        "success": False,
        "provider": "gateway",
        "reviews": {
            "model-1": {"status": "error", "reason": "openai package not installed"},
            "model-2": {"status": "error", "reason": "Unsupported parameter: 'max_tokens'"},
        },
    }


@pytest.mark.covers("FR-01.13/AC07")
def test_failed_leg_reason_is_written_to_the_review(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    _fake_llm_review(monkeypatch, _all_legs_failed())

    got = review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)
    body = Path(got["review_path"]).read_text(encoding="utf-8")

    assert "## model-1 — error" in body
    assert "> Reason: openai package not installed" in body
    assert "> Reason: Unsupported parameter: 'max_tokens'" in body


@pytest.mark.covers("FR-01.13/AC07")
def test_successful_leg_gets_no_reason_line(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    _fake_llm_review(monkeypatch, {
        "success": True, "provider": "openrouter",
        "reviews": {"glm": {"status": "success", "feedback": "fine"}},
    })
    got = review_runner.run_review(tmp_path, snapshot=_SNAPSHOT)
    assert "Reason:" not in Path(got["review_path"]).read_text(encoding="utf-8")


def _write_review(root: Path, body: str) -> None:
    (root / ".shipwright" / "adopt").mkdir(parents=True)
    (root / ".shipwright" / "adopt" / "review.md").write_text(body, encoding="utf-8")


@pytest.mark.covers("FR-01.13/AC07")
def test_validation_warns_when_no_review_leg_succeeded(tmp_path):
    _write_review(tmp_path, "# Adopt Review — gateway\n\n## model-1 — error\n\n_no feedback_\n\n---\n\n"
                            "## model-2 — degraded\n\nx\n")
    warnings = validate_adoption._review_warnings(tmp_path)
    assert len(warnings) == 1 and "no usable review" in warnings[0]


@pytest.mark.covers("FR-01.13/AC07")
def test_validation_is_quiet_for_a_real_or_skipped_review(tmp_path):
    _write_review(tmp_path, "# Adopt Review\n\n## glm — success\n\nfine\n\n## openai — error\n\nx\n")
    assert validate_adoption._review_warnings(tmp_path) == []
    # A documented skip has no leg headings at all - not a failure to warn about.
    _write_review_skipped = tmp_path / ".shipwright" / "adopt" / "review.md"
    _write_review_skipped.write_text("# Adopt Review — SKIPPED\n\nNo key.\n", encoding="utf-8")
    assert validate_adoption._review_warnings(tmp_path) == []
