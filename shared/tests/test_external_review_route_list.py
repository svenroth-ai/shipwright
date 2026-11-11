"""Issue #1034: an ordered route list for the GPT leg that falls through on runtime failure.

Without ``external_review.gpt_leg.routes`` nothing changes; with it, a route that is unavailable OR
fails while running hands the leg to the next route, and every skipped or failed route is recorded.
"""

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for _d in (_SCRIPTS / "lib", _SCRIPTS / "tools"):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import external_review_default_legs as legs  # noqa: E402
import external_review_routes as routes_mod  # noqa: E402
from external_review_routes import gpt_leg_routes, run_route_chain  # noqa: E402

_OK = {"status": "success", "feedback": "fine\nSHIPWRIGHT_VERDICT: approve", "via": "openrouter"}
_QUOTA = {"status": "error", "via": "codex", "reason": "codex exec exited 1: ERROR: You've hit your usage limit"}


def _chain(monkeypatch, routes, results, *, has_openrouter=True, has_openai=True, codex=(True, "")):
    """Run the chain with stub runners; returns (leg result, calls made)."""
    calls = []

    def runner(name):
        def run():
            calls.append(name)
            outcome = results[name]
            if isinstance(outcome, Exception):
                raise outcome
            return dict(outcome)
        return run

    monkeypatch.setattr(routes_mod, "is_codex_available", lambda: codex)
    out = run_route_chain(routes, {n: runner(n) for n in results}, has_openrouter=has_openrouter, has_openai=has_openai)
    return out, calls


@pytest.mark.covers("FR-01.03/AC24")
def test_runtime_failure_falls_through_to_the_next_route_and_records_it(monkeypatch):
    out, calls = _chain(monkeypatch, ["codex", "openrouter"], {"codex": _QUOTA, "openrouter": _OK})
    assert out["status"] == "success" and calls == ["codex", "openrouter"]
    assert [a["route"] for a in out["attempts"]] == ["codex", "openrouter"]
    assert out["attempts"][0]["outcome"] == "error" and "usage limit" in out["attempts"][0]["reason"]
    assert out["attempts"][1]["outcome"] == "success"
    assert out["fallback_reason"].startswith("codex error")


@pytest.mark.covers("FR-01.03/AC24")
def test_unavailable_route_is_skipped_before_the_call(monkeypatch):
    out, calls = _chain(monkeypatch, ["codex", "openrouter"], {"codex": _QUOTA, "openrouter": _OK}, codex=(False, "codex not installed"))
    assert calls == ["openrouter"] and out["status"] == "success"
    assert out["attempts"][0] == {"route": "codex", "outcome": "skipped", "reason": "codex not installed"}


@pytest.mark.covers("FR-01.03/AC24")
def test_first_route_success_stops_the_chain_without_a_fallback_note(monkeypatch):
    out, calls = _chain(monkeypatch, ["codex", "openrouter"], {"codex": {**_OK, "via": "codex"}, "openrouter": _OK})
    assert calls == ["codex"] and "fallback_reason" not in out
    assert out["attempts"] == [{"route": "codex", "outcome": "success"}]


@pytest.mark.covers("FR-01.03/AC24")
def test_every_route_failing_reports_the_last_failure_with_all_attempts(monkeypatch):
    out, _ = _chain(monkeypatch, ["codex", "openrouter"], {"codex": _QUOTA, "openrouter": {"status": "error", "reason": "502"}})
    assert out["status"] == "error" and out["reason"] == "502"
    assert [a["outcome"] for a in out["attempts"]] == ["error", "error"]


@pytest.mark.covers("FR-01.03/AC24")
def test_a_degraded_reply_also_falls_through(monkeypatch):
    degraded = {"status": "degraded", "reason": "provider returned an empty reply"}
    out, calls = _chain(monkeypatch, ["openrouter", "direct"], {"openrouter": degraded, "direct": _OK})
    assert calls == ["openrouter", "direct"] and out["attempts"][0]["outcome"] == "degraded"


@pytest.mark.covers("FR-01.03/AC24")
def test_nothing_available_is_a_skipped_leg_listing_every_reason(monkeypatch):
    out, calls = _chain(monkeypatch, ["codex", "openrouter", "direct"], {"codex": _OK, "openrouter": _OK, "direct": _OK},
                        has_openrouter=False, has_openai=False, codex=(False, "codex not installed"))
    assert calls == [] and out["status"] == "skipped"
    assert "codex not installed" in out["reason"] and "OPENROUTER_API_KEY" in out["reason"]
    assert len(out["attempts"]) == 3


@pytest.mark.covers("FR-01.03/AC24")
def test_a_route_that_raises_does_not_end_the_chain(monkeypatch):
    out, calls = _chain(monkeypatch, ["codex", "openrouter"], {"codex": RuntimeError("boom"), "openrouter": _OK})
    assert calls == ["codex", "openrouter"] and out["status"] == "success"
    assert out["attempts"][0]["reason"] == "boom"


@pytest.mark.covers("FR-01.03/AC24")
@pytest.mark.parametrize(
    ("config", "want"),
    [
        ({}, None),
        ({"external_review": {"gpt_leg": {"provider": "codex"}}}, None),
        ({"external_review": {"gpt_leg": {"routes": ["codex", "openrouter", "direct"]}}}, ["codex", "openrouter", "direct"]),
        ({"external_review": {"gpt_leg": {"routes": ["openrouter", "codex", "openrouter"]}}}, ["openrouter", "codex"]),
        ({"external_review": {"gpt_leg": {"routes": ["nope", "direct"]}}}, ["direct"]),
        ({"external_review": {"gpt_leg": {"routes": []}}}, None),
        ({"external_review": {"gpt_leg": {"routes": "codex"}}}, None),
        ({"external_review": {"gpt_leg": {"routes": [1, None]}}}, None),
        ({"external_review": {"gpt_leg": []}}, None),
        ({"external_review": []}, None),
    ],
)
def test_gpt_leg_routes_resolution_degrades_instead_of_crashing(config, want):
    assert gpt_leg_routes(config) == want


def _run_cli(monkeypatch, tmp_path, config, *, openrouter_key=True):
    """Drive the real main() with the Codex CLI failing at runtime (quota) and OpenRouter answering."""
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "SHIPWRIGHT_REVIEW_MODEL_CODEX"):
        monkeypatch.delenv(key, raising=False)
    if openrouter_key:
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    monkeypatch.chdir(tmp_path)
    import external_review

    plugin_root = tmp_path / "fake-plan"
    (plugin_root / "prompts" / "plan_reviewer").mkdir(parents=True)
    (plugin_root / "prompts" / "plan_reviewer" / "system").write_text("sys", encoding="utf-8")
    (plugin_root / "prompts" / "plan_reviewer" / "user").write_text("## Spec\n{SPEC}\n## Plan\n{PLAN}\n", encoding="utf-8")
    spec, plan = tmp_path / "spec.md", tmp_path / "plan.md"
    spec.write_text("# Spec", encoding="utf-8")
    plan.write_text("# Plan", encoding="utf-8")
    (tmp_path / "shipwright_iterate_config.json").write_text(json.dumps(config), encoding="utf-8")

    seen = []
    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    monkeypatch.setattr(routes_mod, "is_codex_available", lambda: (True, ""))
    monkeypatch.setattr(external_review, "review_codex", lambda *a, **k: seen.append("codex") or dict(_QUOTA))
    monkeypatch.setattr(external_review, "review_with_openrouter",
                        lambda *a, **k: seen.append(a[-1]) or dict(_OK))
    monkeypatch.setattr("sys.argv", [
        "external_review.py", "--mode", "plan", "--spec-file", str(spec), "--plan-file", str(plan),
        "--plugin-root", str(plugin_root), "--project-root", str(tmp_path), "--driver", "claude"])
    return external_review.main, seen


@pytest.mark.covers("FR-01.03/AC24")
def test_cli_codex_quota_falls_through_to_openrouter_and_lists_the_attempts(monkeypatch, tmp_path, capsys):
    main, seen = _run_cli(monkeypatch, tmp_path, {"external_review": {"gpt_leg": {"routes": ["codex", "openrouter"]}}})
    assert main() == 0
    out = json.loads(capsys.readouterr().out)
    openai = out["reviews"]["openai"]
    assert openai["status"] == "success" and sorted(seen) == ["codex", "glm", "openai"]
    assert [a["route"] for a in openai["attempts"]] == ["codex", "openrouter"]
    assert openai["fallback_reason"].startswith("codex error")
    assert out["reviews_succeeded"] == 2 and out["reviews_expected"] == 2 and not out.get("partially_degraded")
    assert out["provider"] != "routes"  # names what answered, never the setting


@pytest.mark.covers("FR-01.03/AC24")
def test_cli_without_routes_keeps_the_terminal_codex_failure(monkeypatch, tmp_path, capsys):
    """Existing configs behave exactly as before: provider codex, codex fails at runtime -> the leg errors."""
    main, seen = _run_cli(monkeypatch, tmp_path, {"external_review": {"gpt_leg": {"provider": "codex"}}})
    assert main() == 0  # GLM still answered
    out = json.loads(capsys.readouterr().out)
    assert out["reviews"]["openai"]["status"] == "error" and "attempts" not in out["reviews"]["openai"]
    assert "openai" not in seen
    assert out["partially_degraded"] is True


@pytest.mark.covers("FR-01.03/AC24")
def test_a_runtime_skipped_last_route_does_not_hide_an_earlier_real_failure(monkeypatch):
    out, _ = _chain(monkeypatch, ["codex", "openrouter"], {"codex": _QUOTA, "openrouter": {"status": "skipped", "reason": "no key"}})
    assert out["status"] == "error" and "usage limit" in out["reason"]
    assert [a["outcome"] for a in out["attempts"]] == ["error", "skipped"]


@pytest.mark.covers("FR-01.03/AC24")
def test_an_unknown_runner_status_counts_as_a_failure(monkeypatch):
    out, calls = _chain(monkeypatch, ["openrouter", "direct"], {"openrouter": {"status": "weird"}, "direct": _OK})
    assert calls == ["openrouter", "direct"] and out["attempts"][0]["outcome"] == "error"


@pytest.mark.covers("FR-01.03/AC24")
def test_codex_only_operator_with_a_routes_list_counts_as_configured(monkeypatch):
    """No API keys, provider left at its default, routes name codex and codex answers -> not missing_keys."""
    import external_review_config as cfg

    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    assert cfg._codex_route_reachable({"external_review": {"gpt_leg": {"routes": ["codex", "openrouter"]}}})
    assert not cfg._codex_route_reachable({"external_review": {"gpt_leg": {"routes": ["openrouter"]}}})
