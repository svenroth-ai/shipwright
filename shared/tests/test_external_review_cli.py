"""Golden-master regression tests for shared/scripts/tools/external_review.py.

Locks in the CLI behavior of the external review entry point against the
historical plan-side ``review.py``: same JSON output schema, same provider
detection, same prompt loading per mode, same fallback semantics.

Six core scenarios cover the provider-detect matrix:
1. No keys           → provider="none",       both reviews skipped
2. Only OPENROUTER   → provider="openrouter", both reviews via OpenRouter
3. Only GEMINI       → provider="direct",     gemini direct, openai skipped
4. Only OPENAI       → provider="direct",     openai direct, gemini skipped
5. Both direct keys  → provider="direct",     both run via direct APIs
6. OpenRouter wins   → provider="openrouter", direct keys ignored
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add tools/ to path so we can import external_review as a module
_TOOLS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))


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
    """Fake plan plugin tree with prompts/plan_reviewer/ + spec.md + plan.md."""
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


# ---- detect_provider — provider detection matrix ----

def test_detect_provider_none(clean_env):
    import external_review

    assert external_review.detect_provider() == "none"


def test_detect_provider_openrouter(monkeypatch, clean_env):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review

    assert external_review.detect_provider() == "openrouter"


def test_detect_provider_direct_gemini(monkeypatch, clean_env):
    monkeypatch.setenv("GEMINI_API_KEY", "AI-test")
    import external_review

    assert external_review.detect_provider() == "direct"


def test_detect_provider_direct_google(monkeypatch, clean_env):
    """Both GEMINI_API_KEY and GOOGLE_API_KEY count as a Gemini direct key."""
    monkeypatch.setenv("GOOGLE_API_KEY", "AI-test")
    import external_review

    assert external_review.detect_provider() == "direct"


def test_detect_provider_direct_openai(monkeypatch, clean_env):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    import external_review

    assert external_review.detect_provider() == "direct"


def test_detect_provider_openrouter_wins_over_direct(monkeypatch, clean_env):
    """OpenRouter takes precedence even when direct keys are also set."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("GEMINI_API_KEY", "AI-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    import external_review

    assert external_review.detect_provider() == "openrouter"


# ---- Subprocess full-flow: no keys → graceful skip ----

def test_cli_no_keys_returns_skipped_schema(tmp_path, fake_plan_plugin, monkeypatch):
    """End-to-end: invoke CLI subprocess without any API keys.

    Asserts the JSON schema:
        { "success": bool, "provider": "none", "reviews": { "gemini": {...}, "openai": {...} } }

    Both reviews must report status=skipped.
    """
    monkeypatch.chdir(tmp_path)
    plugin_root, spec, plan = fake_plan_plugin

    # Strip every credential the script might pick up.
    env = {
        k: v for k, v in {
            **__import__("os").environ,
        }.items()
        if k not in {
            "OPENROUTER_API_KEY",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "OPENAI_API_KEY",
        }
    }
    # Force load_shipwright_env to operate inside an empty dir.
    env["PWD"] = str(tmp_path)

    cli = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "external_review.py"

    result = subprocess.run(
        [sys.executable, str(cli),
         "--mode", "iterate",
         "--spec-file", str(spec),
         "--plan-file", str(plan),
         "--plugin-root", str(plugin_root)],
        capture_output=True,
        text=True,
        env=env,
        cwd=tmp_path,
    )

    assert result.returncode == 0, f"stderr: {result.stderr}"
    payload = json.loads(result.stdout)

    # Schema lock-in
    assert "success" in payload
    assert "provider" in payload
    assert "reviews" in payload
    assert payload["provider"] == "none"
    assert payload["success"] is True

    # Both reviews must be in the reviews block, both with status=skipped
    assert set(payload["reviews"].keys()) == {"gemini", "openai"}
    assert payload["reviews"]["gemini"]["status"] == "skipped"
    assert payload["reviews"]["openai"]["status"] == "skipped"


# ---- In-process: prompt loading per mode ----

def test_main_iterate_mode_loads_iterate_prompts(
    monkeypatch, clean_env, capsys, fake_plan_plugin, tmp_path
):
    """--mode iterate must call load_iterate_review_prompts (not plan)."""
    plugin_root, spec, plan = fake_plan_plugin

    import external_review

    iterate_called = []
    plan_called = []

    def fake_iterate(prompts_root=None):
        iterate_called.append(prompts_root)
        return ("ITERATE_SYSTEM", "iterate user with {SPEC} and {PLAN}")

    def fake_plan(plugin_root):
        plan_called.append(plugin_root)
        return ("PLAN_SYSTEM", "plan user with {SPEC} and {PLAN}")

    monkeypatch.setattr(external_review, "load_iterate_review_prompts", fake_iterate)
    monkeypatch.setattr(external_review, "load_plan_review_prompts", fake_plan)

    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", "iterate",
         "--spec-file", str(spec),
         "--plan-file", str(plan),
         "--plugin-root", str(plugin_root)],
    )

    rc = external_review.main()
    assert rc == 0
    # iterate-mode → only iterate loader fired
    assert len(iterate_called) == 1
    assert len(plan_called) == 0


def test_main_plan_mode_loads_plan_prompts(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """--mode plan must call load_plan_review_prompts (not iterate)."""
    plugin_root, spec, plan = fake_plan_plugin

    import external_review

    iterate_called = []
    plan_called = []

    def fake_iterate(prompts_root=None):
        iterate_called.append(prompts_root)
        return ("ITERATE_SYSTEM", "iterate {SPEC} {PLAN}")

    def fake_plan(plugin_root):
        plan_called.append(plugin_root)
        return ("PLAN_SYSTEM", "plan {SPEC} {PLAN}")

    monkeypatch.setattr(external_review, "load_iterate_review_prompts", fake_iterate)
    monkeypatch.setattr(external_review, "load_plan_review_prompts", fake_plan)

    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", "plan",
         "--spec-file", str(spec),
         "--plan-file", str(plan),
         "--plugin-root", str(plugin_root)],
    )

    rc = external_review.main()
    assert rc == 0
    # plan-mode → only plan loader fired
    assert len(plan_called) == 1
    assert len(iterate_called) == 0


# ---- Output schema lock-in ----

def test_main_output_schema_has_expected_keys(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """JSON output must always contain success/provider/reviews keys."""
    plugin_root, spec, plan = fake_plan_plugin

    import external_review

    monkeypatch.setattr(
        external_review,
        "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "user {SPEC} {PLAN}"),
    )

    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", "iterate",
         "--spec-file", str(spec),
         "--plan-file", str(plan),
         "--plugin-root", str(plugin_root)],
    )

    external_review.main()
    out = capsys.readouterr().out
    payload = json.loads(out)

    # Top-level
    assert "success" in payload
    assert "provider" in payload
    assert "reviews" in payload

    # Reviews always has both keys, even when skipped
    assert "gemini" in payload["reviews"]
    assert "openai" in payload["reviews"]

    # Each review has at least 'status'
    for name in ("gemini", "openai"):
        assert "status" in payload["reviews"][name]


# ---- Argparse / CLI surface ----

def test_main_missing_plan_file_exits_with_error(monkeypatch, clean_env, fake_plan_plugin):
    plugin_root, spec, _plan = fake_plan_plugin
    nonexistent = plugin_root / "nope" / "missing.md"

    import external_review

    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", "iterate",
         "--spec-file", str(spec),
         "--plan-file", str(nonexistent),
         "--plugin-root", str(plugin_root)],
    )

    rc = external_review.main()
    assert rc != 0


def test_main_missing_spec_file_exits_with_error(monkeypatch, clean_env, fake_plan_plugin):
    plugin_root, _spec, plan = fake_plan_plugin
    nonexistent = plugin_root / "nope" / "missing.md"

    import external_review

    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", "iterate",
         "--spec-file", str(nonexistent),
         "--plan-file", str(plan),
         "--plugin-root", str(plugin_root)],
    )

    rc = external_review.main()
    assert rc != 0


# ---- Module-level imports load cleanly ----

def test_external_review_module_imports_cleanly():
    """Smoke: the module must be importable without side-effects breaking."""
    import external_review

    assert hasattr(external_review, "main")
    assert hasattr(external_review, "detect_provider")
    assert hasattr(external_review, "review_with_openrouter")
    assert hasattr(external_review, "review_with_gemini")
    assert hasattr(external_review, "review_with_openai")


# ---- Provider call-path coverage (mocked) ----
#
# These tests prove the CLI dispatches the right review functions for each
# detect_provider() outcome and that the JSON output has the right shape per
# scenario. The provider helpers themselves get monkey-patched with sentinels
# that record their calls and return a known-shape success blob.


def _patch_review_funcs(monkeypatch, external_review):
    """Replace review_with_* with sentinels that record calls and return a known blob."""
    calls = {"openrouter": [], "gemini": [], "openai": []}

    def fake_openrouter(plan, spec, sys_p, usr_p, cfg, model_key):
        calls["openrouter"].append(model_key)
        return {"status": "success", "feedback": f"OR-{model_key}", "via": "openrouter"}

    def fake_gemini(plan, spec, sys_p, usr_p, cfg):
        calls["gemini"].append("gemini")
        return {"status": "success", "feedback": "G-direct", "via": "direct"}

    def fake_openai(plan, spec, sys_p, usr_p, cfg):
        calls["openai"].append("openai")
        return {"status": "success", "feedback": "O-direct", "via": "direct"}

    monkeypatch.setattr(external_review, "review_with_openrouter", fake_openrouter)
    monkeypatch.setattr(external_review, "review_with_gemini", fake_gemini)
    monkeypatch.setattr(external_review, "review_with_openai", fake_openai)
    return calls


def _run_main(monkeypatch, fake_plan_plugin, mode="iterate"):
    """Invoke external_review.main() with the fake plugin fixture and return parsed JSON."""
    plugin_root, spec, plan = fake_plan_plugin
    import external_review

    monkeypatch.setattr(
        external_review,
        "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys-iterate", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(
        external_review,
        "load_plan_review_prompts",
        lambda plugin_root: ("sys-plan", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py",
         "--mode", mode,
         "--spec-file", str(spec),
         "--plan-file", str(plan),
         "--plugin-root", str(plugin_root)],
    )
    rc = external_review.main()
    return rc, external_review


def test_main_openrouter_path_dispatches_both_via_openrouter(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """OPENROUTER_API_KEY set → both reviews go via review_with_openrouter."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    calls = _patch_review_funcs(monkeypatch, external_review)

    rc, _ = _run_main(monkeypatch, fake_plan_plugin, mode="iterate")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "openrouter"
    assert payload["success"] is True
    assert sorted(calls["openrouter"]) == ["gemini", "openai"]
    assert calls["gemini"] == []
    assert calls["openai"] == []
    assert payload["reviews"]["gemini"]["status"] == "success"
    assert payload["reviews"]["gemini"]["feedback"] == "OR-gemini"
    assert payload["reviews"]["openai"]["feedback"] == "OR-openai"


def test_main_direct_gemini_only_path(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """Only GEMINI_API_KEY → review_with_gemini fires; review_with_openai still called but skips."""
    monkeypatch.setenv("GEMINI_API_KEY", "AI-test")
    import external_review
    calls = _patch_review_funcs(monkeypatch, external_review)

    rc, _ = _run_main(monkeypatch, fake_plan_plugin, mode="iterate")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "direct"
    assert calls["openrouter"] == []
    assert calls["gemini"] == ["gemini"]
    assert calls["openai"] == ["openai"]  # Always invoked in direct mode; the helper handles the missing-key skip
    assert payload["reviews"]["gemini"]["feedback"] == "G-direct"


def test_main_direct_openai_only_path(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """Only OPENAI_API_KEY → review_with_openai fires."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    import external_review
    calls = _patch_review_funcs(monkeypatch, external_review)

    rc, _ = _run_main(monkeypatch, fake_plan_plugin, mode="iterate")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "direct"
    assert calls["openrouter"] == []
    assert calls["openai"] == ["openai"]
    assert payload["reviews"]["openai"]["feedback"] == "O-direct"


def test_main_both_direct_keys_dispatches_both(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """Both direct keys set, no OPENROUTER → both direct review functions fire."""
    monkeypatch.setenv("GEMINI_API_KEY", "AI-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    import external_review
    calls = _patch_review_funcs(monkeypatch, external_review)

    rc, _ = _run_main(monkeypatch, fake_plan_plugin, mode="iterate")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "direct"
    assert calls["openrouter"] == []
    assert calls["gemini"] == ["gemini"]
    assert calls["openai"] == ["openai"]
    assert payload["reviews"]["gemini"]["status"] == "success"
    assert payload["reviews"]["openai"]["status"] == "success"


def test_main_openrouter_wins_over_direct(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """OPENROUTER + direct keys all set → only OpenRouter is used (precedence)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.setenv("GEMINI_API_KEY", "AI-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    import external_review
    calls = _patch_review_funcs(monkeypatch, external_review)

    rc, _ = _run_main(monkeypatch, fake_plan_plugin, mode="iterate")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "openrouter"
    assert sorted(calls["openrouter"]) == ["gemini", "openai"]
    assert calls["gemini"] == []
    assert calls["openai"] == []


def test_main_plan_mode_with_openrouter(
    monkeypatch, clean_env, capsys, fake_plan_plugin
):
    """--mode plan + OPENROUTER → OpenRouter path runs, plan prompts loaded."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review
    calls = _patch_review_funcs(monkeypatch, external_review)

    rc, _ = _run_main(monkeypatch, fake_plan_plugin, mode="plan")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["provider"] == "openrouter"
    assert sorted(calls["openrouter"]) == ["gemini", "openai"]
