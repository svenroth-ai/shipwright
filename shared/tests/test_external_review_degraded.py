"""Regression tests for the external-review DEGRADED gate (SS6).

Covers the SS6 bug: a live /shipwright-plan run silently fell back to
self-review because Gemini's key was missing AND the direct OpenAI call
errored on an incompatible param. The review gate degraded WITHOUT failing
loudly — ``main()`` hardcoded ``success: true`` regardless of whether a
single review actually ran, so the caller marked the gate "completed".

Guarantee locked in here: when a provider is attempted (keys present) but
ZERO reviews succeed, the CLI fails loud — ``success: false``,
``degraded: true``, a recorded ``degraded_reason``, a stderr banner, and a
non-zero exit code. It can no longer silently no-op.

The companion ``max_tokens → max_completion_tokens`` param fix is covered by
``test_external_review_openai_param.py``.
"""

import json
import sys
from pathlib import Path

import pytest

# Add tools/ + lib/ to path so we can import external_review + its helpers.
_TOOLS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "tools"
_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
for _d in (_TOOLS_DIR, _LIB_DIR):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    """Isolated env: no keys, no model overrides, chdir to empty dir."""
    monkeypatch.chdir(tmp_path)
    for key in (
        "OPENROUTER_API_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "SHIPWRIGHT_REVIEW_MODEL_GEMINI",
        "SHIPWRIGHT_REVIEW_MODEL_CHATGPT",
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_GEMINI",
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_CHATGPT",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def fake_plan_plugin(tmp_path):
    """Fake plan plugin tree with prompts + spec.md + plan.md."""
    plugin_root = tmp_path / "fake-plan"
    (plugin_root / "prompts" / "plan_reviewer").mkdir(parents=True)
    (plugin_root / "prompts" / "plan_reviewer" / "system").write_text(
        "You are a senior reviewer for plans.", encoding="utf-8"
    )
    (plugin_root / "prompts" / "plan_reviewer" / "user").write_text(
        "Review:\n## Spec\n{SPEC}\n## Plan\n{PLAN}\n", encoding="utf-8"
    )
    spec = tmp_path / "spec.md"
    plan = tmp_path / "plan.md"
    spec.write_text("# Spec\nDo X.", encoding="utf-8")
    plan.write_text("# Plan\nStep 1.", encoding="utf-8")
    return plugin_root, spec, plan


def _run_main_direct(monkeypatch, fake_plan_plugin, gemini_result, openai_result):
    """Drive main() in 'direct' provider mode with stubbed review helpers."""
    plugin_root, spec, plan = fake_plan_plugin
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")  # → provider 'direct'

    import external_review

    monkeypatch.setattr(
        external_review,
        "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(
        external_review, "review_with_gemini", lambda *a, **k: dict(gemini_result)
    )
    monkeypatch.setattr(
        external_review, "review_with_openai", lambda *a, **k: dict(openai_result)
    )
    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", "iterate",
         "--spec-file", str(spec),
         "--plan-file", str(plan),
         "--plugin-root", str(plugin_root)],
    )
    return external_review.main()


def test_gate_degraded_when_keys_present_but_no_review_succeeds(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """The exact live bug: gemini key missing (skipped) + openai errors.

    provider='direct', 0/2 reviews succeed → must fail loud, NOT success:true.
    """
    rc = _run_main_direct(
        monkeypatch,
        fake_plan_plugin,
        gemini_result={"status": "skipped", "reason": "No GEMINI_API_KEY set"},
        openai_result={"status": "error", "reason": "Unsupported parameter: max_tokens"},
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 1, "degraded gate must exit non-zero"
    assert payload["success"] is False
    assert payload["degraded"] is True
    assert payload["provider"] == "direct"
    assert payload["reviews_succeeded"] == 0
    assert payload.get("degraded_reason")
    # The recorded reason must surface WHY each leg failed (machine-readable).
    assert "max_tokens" in payload["degraded_reason"]
    assert "GEMINI_API_KEY" in payload["degraded_reason"]
    # And a loud human-facing banner on stderr.
    assert "DEGRADED" in captured.err


def test_gate_not_degraded_on_partial_success(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """One reviewer succeeding = a functioning gate (not a no-op)."""
    rc = _run_main_direct(
        monkeypatch,
        fake_plan_plugin,
        gemini_result={"status": "skipped", "reason": "No GEMINI_API_KEY set"},
        openai_result={"status": "success", "feedback": "looks fine", "via": "direct"},
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["success"] is True
    assert payload["degraded"] is False
    assert payload["reviews_succeeded"] == 1


def test_no_keys_is_not_degraded(monkeypatch, clean_env, capsys, fake_plan_plugin):
    """provider='none' (no keys) is the explicit missing-keys state, NOT a
    degraded gate — the caller handles it via get_external_review_status."""
    plugin_root, spec, plan = fake_plan_plugin
    import external_review

    monkeypatch.setattr(
        external_review,
        "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", "iterate",
         "--spec-file", str(spec),
         "--plan-file", str(plan),
         "--plugin-root", str(plugin_root)],
    )
    rc = external_review.main()
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["provider"] == "none"
    assert payload["success"] is True
    assert payload["degraded"] is False


def test_empty_diff_short_circuit_is_not_degraded(
    monkeypatch, clean_env, capsys, tmp_path
):
    """Empty diff → legitimate skip, exit 0, not degraded (schema carries flag)."""
    diff = tmp_path / "diff.patch"
    spec = tmp_path / "spec.md"
    diff.write_text("   \n", encoding="utf-8")
    spec.write_text("# spec", encoding="utf-8")
    plugin_root = tmp_path / "pr"
    plugin_root.mkdir()

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review

    monkeypatch.setattr(
        external_review,
        "load_code_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {DIFF}"),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", "code",
         "--spec-file", str(spec),
         "--diff-file", str(diff),
         "--plugin-root", str(plugin_root)],
    )
    rc = external_review.main()
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload.get("skipped") == "empty_diff"
    assert payload["degraded"] is False


def test_finalize_review_output_helper_contract():
    """The shared helper is the single source of the degraded decision."""
    from external_review_degraded import finalize_review_output

    # Attempted + no success → degraded, exit 1.
    out, code = finalize_review_output(
        "direct",
        {"gemini": {"status": "skipped", "reason": "no key"},
         "openai": {"status": "error", "reason": "boom"}},
    )
    assert code == 1
    assert out["degraded"] is True
    assert out["success"] is False

    # Attempted + one success → healthy, exit 0.
    out, code = finalize_review_output(
        "openrouter",
        {"gemini": {"status": "success", "feedback": "ok"},
         "openai": {"status": "error", "reason": "boom"}},
    )
    assert code == 0
    assert out["degraded"] is False
    assert out["success"] is True

    # No provider attempted → never degraded.
    out, code = finalize_review_output(
        "none",
        {"gemini": {"status": "skipped"}, "openai": {"status": "skipped"}},
    )
    assert code == 0
    assert out["degraded"] is False
    assert out["success"] is True
