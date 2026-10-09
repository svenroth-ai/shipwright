"""The gateway route reaches every external-review path, not only Adopt (#547).

``test_llm_review_gateway*.py`` cover the gateway leg and ``llm_review.run_review``.
This file covers what the follow-up reported as unwired: the
``external_review.py`` CLI that plan / iterate / build / security shell out to,
the key-availability gate that decides Branch A vs. Branch B, the review marker
that records the pass, the token-limit parameter, and the non-secret evidence.
All HTTP is mocked; there is no real gateway to test against from this repo.
"""

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for _sub in ("tools", "lib", "checks"):
    _p = str(_SCRIPTS / _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)

_GATEWAY_ENV = (
    "SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL",
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1",
    "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1",
    "SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2",
    "SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2",
    "SHIPWRIGHT_REVIEW_GATEWAY_HEADER_CF_ACCESS_CLIENT_ID",
    "SHIPWRIGHT_REVIEW_GATEWAY_HEADER_CF_ACCESS_CLIENT_SECRET",
)


@pytest.fixture
def gateway_env(monkeypatch, tmp_path):
    """Gateway fully configured, every other provider key absent."""
    monkeypatch.chdir(tmp_path)
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "CODEXTENDER_ACTIVE", *_GATEWAY_ENV):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL", "https://gw.example.com/v1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_1", "alias-one")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_1", "vk-secret-1")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_MODEL_2", "alias-two")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_KEY_MODEL_2", "vk-secret-2")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_CF_ACCESS_CLIENT_ID", "waf-id-value")
    monkeypatch.setenv("SHIPWRIGHT_REVIEW_GATEWAY_HEADER_CF_ACCESS_CLIENT_SECRET", "waf-secret-value")


@pytest.fixture
def review_inputs(tmp_path):
    plugin_root = tmp_path / "fake-plan"
    (plugin_root / "prompts" / "plan_reviewer").mkdir(parents=True)
    spec = tmp_path / "spec.md"
    plan = tmp_path / "plan.md"
    spec.write_text("# Spec\nDo X.", encoding="utf-8")
    plan.write_text("# Plan\nStep 1.", encoding="utf-8")
    return plugin_root, spec, plan


def _run_cli(monkeypatch, review_inputs, mode="iterate"):
    plugin_root, spec, plan = review_inputs
    import external_review

    monkeypatch.setattr(
        external_review, "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py", "--mode", mode, "--spec-file", str(spec),
         "--plan-file", str(plan), "--plugin-root", str(plugin_root), "--driver", "claude"],
    )
    return external_review, external_review.main


@pytest.mark.covers("FR-01.13/AC07")
def test_cli_routes_a_gateway_only_operator_through_the_gateway(
    monkeypatch, gateway_env, review_inputs, capsys
):
    """The reported defect: gateway vars set, no OpenRouter/OpenAI key -> the
    CLI said provider 'none' and skipped both legs."""
    external_review, main = _run_cli(monkeypatch, review_inputs)
    seen = []

    def fake_leg(prompt, system_prompt, slot, timeout, max_retries=None):
        seen.append((slot, prompt))
        return {"status": "success", "feedback": "ok", "via": "gateway", "answering_model": f"real-{slot}"}

    import external_review_gateway_cli
    monkeypatch.setattr(external_review_gateway_cli, "review_gateway_prompt", fake_leg)
    rc = main()
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["provider"] == "gateway"
    assert set(payload["reviews"]) == {"model-1", "model-2"}
    assert payload["reviews_succeeded"] == 2
    assert payload["reviewed"] is True
    assert payload["reviews"]["model-2"]["answering_model"] == "real-2"
    assert sorted(slot for slot, _ in seen) == ["1", "2"]
    assert all("Do X." in prompt and "Step 1." in prompt for _, prompt in seen)  # rendered, not raw


@pytest.mark.covers("FR-01.13/AC07")
def test_cli_gateway_is_exclusive_and_fails_closed(
    monkeypatch, gateway_env, review_inputs, capsys
):
    """A failing gateway must not fall back to OpenRouter/direct even when
    those keys are also set - an egress policy would call that a violation."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-key")
    external_review, main = _run_cli(monkeypatch, review_inputs)
    import external_review_gateway_cli
    monkeypatch.setattr(
        external_review_gateway_cli, "review_gateway_prompt",
        lambda *a, **k: {"status": "error", "reason": "gateway down"},
    )
    for name in ("review_with_openrouter", "review_with_openai"):
        monkeypatch.setattr(
            external_review, name,
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("fell back off the gateway")),
        )
    rc = main()
    payload = json.loads(capsys.readouterr().out)

    assert rc == 1
    assert payload["success"] is False and payload["degraded"] is True
    assert payload["provider"] == "gateway"
    assert payload["reviewed"] is False


@pytest.mark.covers("FR-01.13/AC07")
def test_cli_detect_provider_names_the_gateway(monkeypatch, gateway_env):
    import external_review

    assert external_review.detect_provider() == "gateway"
    monkeypatch.delenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL")
    assert external_review.detect_provider() == "none"


@pytest.mark.covers("FR-01.13/AC07")
def test_nothing_attempted_is_not_reported_as_reviewed(monkeypatch, tmp_path, review_inputs, capsys):
    """`success: true` with nothing reviewed is kept (provider 'none' is the
    explicit missing-keys state), but it must no longer look like a pass."""
    monkeypatch.chdir(tmp_path)
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "CODEXTENDER_ACTIVE", *_GATEWAY_ENV):
        monkeypatch.delenv(key, raising=False)
    _external_review, main = _run_cli(monkeypatch, review_inputs)
    rc = main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 0 and payload["success"] is True
    assert payload["reviewed"] is False and payload["reviews_succeeded"] == 0
    assert "did NOT run" in captured.err


@pytest.mark.covers("FR-01.13/AC07")
def test_gateway_counts_as_an_available_route(monkeypatch, gateway_env):
    """Otherwise the skills take Branch B and prompt for an API key although a
    gateway is already configured."""
    import external_review_config as cfg

    config = cfg.load_review_config()
    assert cfg.get_external_review_status(config) == "available"
    assert cfg.is_external_review_enabled(config) is True
    monkeypatch.delenv("SHIPWRIGHT_REVIEW_GATEWAY_BASE_URL")
    assert cfg.get_external_review_status(config) == "missing_keys"


@pytest.mark.covers("FR-01.13/AC07")
def test_key_check_reports_the_gateway(monkeypatch, gateway_env, capsys):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "check_external_review_keys", _SCRIPTS / "checks" / "check-external-review-keys.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr("sys.argv", ["check-external-review-keys.py", "--project-root", "."])
    assert module.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["available"] is True and out["providers"]["gateway"] is True


@pytest.mark.covers("FR-01.13/AC07")
def test_empty_diff_envelope_uses_the_gateway_roster(gateway_env):
    from external_review_empty import empty_diff_envelope

    envelope = empty_diff_envelope("claude", {"driver": "claude"})
    assert set(envelope["reviews"]) == {"model-1", "model-2"}


@pytest.mark.covers("FR-01.13/AC07")
def test_gateway_roster_has_its_own_marker_schema(tmp_path):
    """Until schema 6 the gateway could answer a review but no marker could
    record it, so the gate read the pass as unreviewed."""
    from lib.review_companion import write_markers
    from lib.review_marker import GATEWAY_MARKER_SCHEMA, STATE_BLOCK, evaluate_review_state

    verdicts = {"model-1": "approve", "model-2": "revise"}
    paths = write_markers(
        tmp_path, "run-1", "plan", marker_status="completed",
        record_status="completed", findings_count=1, verdicts=verdicts,
    )
    marker = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert marker["marker_schema"] == GATEWAY_MARKER_SCHEMA == 6
    assert evaluate_review_state(marker)[0] != STATE_BLOCK
    # A glm/openai roster under schema 6 is a mismatch, not a pass.
    marker["verdicts"] = {"glm": "approve", "openai": "approve"}
    assert evaluate_review_state(marker)[0] == STATE_BLOCK
