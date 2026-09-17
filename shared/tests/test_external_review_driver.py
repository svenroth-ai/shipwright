"""Regression tests for ``--driver`` (shared/scripts/tools/external_review.py):
the required-flag contract, the {glm, opus} roster under ``--driver codex``,
the empty-diff short-circuit building its skip-shape from the SELECTED
roster, and the ``gpt_leg.provider`` non-leak guard (Decision #4 in the
opus-review-leg-codex-driver mini-plan — an unrelated cost-routing knob for
the 'openai' identity must never leak an 'openai' leg into a driver=codex
roster).

Split out of ``test_external_review_cli.py`` (already large) rather than
grown further — mirrors the existing
test_external_review_codex_leg.py / test_external_review_codex_availability.py
split.
"""

import json
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in (
        "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def fake_plan_plugin(tmp_path):
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


@pytest.fixture
def fake_code_inputs(tmp_path):
    diff = tmp_path / "diff.patch"
    spec = tmp_path / "spec.md"
    diff.write_text("diff --git a/foo.py b/foo.py\n@@ -1,1 +1,1 @@\n-old\n+new\n", encoding="utf-8")
    spec.write_text("# Section spec\n- Do X.\n", encoding="utf-8")
    return diff, spec


def _argv(plugin_root, spec, plan, mode="iterate", driver=None):
    argv = ["external_review.py", "--mode", mode, "--spec-file", str(spec),
            "--plan-file", str(plan), "--plugin-root", str(plugin_root)]
    if driver is not None:
        argv += ["--driver", driver]
    return argv


# --- --driver is required, no default ---------------------------------------

def test_driver_is_required_no_default(monkeypatch, clean_env, fake_plan_plugin):
    plugin_root, spec, plan = fake_plan_plugin
    import external_review

    monkeypatch.setattr("sys.argv", _argv(plugin_root, spec, plan, driver=None))
    with pytest.raises(SystemExit) as exc:
        external_review.main()
    assert exc.value.code == 2


@pytest.mark.parametrize("driver", ["claude", "codex"])
def test_driver_accepts_both_documented_choices(monkeypatch, clean_env, fake_plan_plugin, driver):
    """With no keys/CLI available, either driver must parse and skip cleanly
    (rc == 0, nothing attempted) — never crash on an unresolved argparse
    choice. Mocks the opus leg unavailable so this stays isolated from
    whatever `claude` binary happens to be on the test machine's PATH."""
    plugin_root, spec, plan = fake_plan_plugin
    import external_review
    import external_review_opus_leg as opus_legs

    monkeypatch.setattr(
        external_review, "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(opus_legs, "is_claude_cli_available", lambda: (False, "not installed"))
    monkeypatch.setattr("sys.argv", _argv(plugin_root, spec, plan, driver=driver))
    rc = external_review.main()
    assert rc == 0


def test_driver_rejects_an_unknown_value(monkeypatch, clean_env, fake_plan_plugin):
    plugin_root, spec, plan = fake_plan_plugin
    import external_review

    monkeypatch.setattr("sys.argv", _argv(plugin_root, spec, plan, driver="gemini"))
    with pytest.raises(SystemExit) as exc:
        external_review.main()
    assert exc.value.code == 2


# --- --driver codex selects {glm, opus}, never {glm, openai} ---------------

@pytest.mark.covers("FR-01.11/AC30")
def test_driver_codex_dispatches_opus_not_openai(monkeypatch, clean_env, capsys, fake_plan_plugin):
    plugin_root, spec, plan = fake_plan_plugin
    import external_review
    import external_review_opus_leg as opus_legs

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setattr(
        external_review, "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(opus_legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(
        external_review, "review_claude_cli",
        lambda *_a, **_k: {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve", "via": "claude_cli"},
    )
    glm_calls = []

    def fake_openrouter(_plan, _spec, _sys_p, _usr_p, _cfg, model_key):
        glm_calls.append(model_key)
        return {"status": "success", "feedback": f"OR-{model_key}", "via": "openrouter"}

    monkeypatch.setattr(external_review, "review_with_openrouter", fake_openrouter)
    monkeypatch.setattr("sys.argv", _argv(plugin_root, spec, plan, driver="codex"))

    rc = external_review.main()
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["driver"] == "codex"
    assert set(payload["reviews"].keys()) == {"glm", "opus"}
    assert "openai" not in payload["reviews"]
    assert payload["reviews"]["opus"]["via"] == "claude_cli"
    assert payload["provider"] == "claude_cli"
    assert glm_calls == ["glm"]
    assert payload["reviews"]["glm"]["via"] == "openrouter"


@pytest.mark.covers("FR-01.11/AC30")
def test_driver_claude_keeps_todays_openai_roster(monkeypatch, clean_env, capsys, fake_plan_plugin):
    plugin_root, spec, plan = fake_plan_plugin
    import external_review

    monkeypatch.setattr(
        external_review, "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr("sys.argv", _argv(plugin_root, spec, plan, driver="claude"))

    rc = external_review.main()
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["driver"] == "claude"
    assert set(payload["reviews"].keys()) == {"glm", "openai"}
    assert "opus" not in payload["reviews"]


# --- gpt_leg.provider must never leak an 'openai' leg into driver=codex -----

def test_gpt_leg_provider_codex_config_has_no_effect_under_driver_codex(
    monkeypatch, clean_env, capsys, fake_plan_plugin, tmp_path,
):
    """Decision #4: `external_review.gpt_leg.provider == "codex"` is an
    unrelated cost-routing knob for the 'openai' identity. It must have ZERO
    effect on a --driver codex run's roster — resolve_openai_route must never
    even be called on that path."""
    plugin_root, spec, plan = fake_plan_plugin
    (tmp_path / "shipwright_iterate_config.json").write_text(
        json.dumps({"external_review": {"gpt_leg": {"provider": "codex"}}}), encoding="utf-8",
    )
    import external_review
    import external_review_opus_leg as opus_legs

    def _boom(*_a, **_k):
        raise AssertionError("resolve_openai_route must not be called when --driver codex")

    monkeypatch.setattr(external_review, "resolve_openai_route", _boom)
    monkeypatch.setattr(opus_legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(
        external_review, "review_claude_cli",
        lambda *_a, **_k: {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve", "via": "claude_cli"},
    )
    monkeypatch.setattr(
        external_review, "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr("sys.argv", _argv(plugin_root, spec, plan, driver="codex") + ["--project-root", str(tmp_path)])

    rc = external_review.main()
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert set(payload["reviews"].keys()) == {"glm", "opus"}


# --- empty-diff short-circuit builds its skip-shape from the roster --------

def test_driver_codex_empty_diff_skips_opus_not_openai(
    monkeypatch, clean_env, capsys, fake_plan_plugin, fake_code_inputs,
):
    plugin_root, _spec_unused, _plan_unused = fake_plan_plugin
    diff, spec = fake_code_inputs
    diff.write_text("   \n", encoding="utf-8")
    import external_review

    argv = ["external_review.py", "--mode", "code", "--spec-file", str(spec),
            "--diff-file", str(diff), "--plugin-root", str(plugin_root),
            "--driver", "codex"]
    monkeypatch.setattr("sys.argv", argv)

    rc = external_review.main()
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload.get("skipped") == "empty_diff"
    assert payload["driver"] == "codex"
    assert set(payload["reviews"].keys()) == {"glm", "opus"}
    assert payload["reviews"]["opus"] == {"status": "skipped", "reason": "empty diff"}
