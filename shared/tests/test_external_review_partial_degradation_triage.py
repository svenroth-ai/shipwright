"""Automatic triage filing for a silently-degraded reviewer arm.

Companion to `test_external_review_reply.py`'s `partially_degraded` field:
the field alone is only loud to something that reads the CLI's JSON/stderr.
Nothing did — DeepSeek's arm degraded across every sampled iterate run from
2026-08-13 to 2026-08-31 while GPT quietly carried the cascade, unnoticed
until a manual audit. `external_review.py::main` now files a triage card
itself when a leg degrades, so the signal survives even when nobody is
reading this particular run's stderr.
"""

import json
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "tools"
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
for _d in (_TOOLS_DIR, _SCRIPTS_DIR, _LIB_DIR):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import triage  # noqa: E402
from external_review_degraded import file_partial_degradation_triage  # noqa: E402
from triage import read_all_items  # noqa: E402


def test_one_legs_filing_failure_does_not_suppress_the_others(monkeypatch, tmp_path):
    """Each leg files independently — the two-reviewer roster today means
    `legs` is only ever length 1 in practice, but the helper itself must not
    silently drop a later leg's card because an earlier one raised."""
    real_append = triage.append_triage_item_idempotent
    calls: list[str] = []

    def _flaky_append(project_root, **kwargs):
        calls.append(kwargs["dedup_key"])
        if kwargs["dedup_key"].endswith("deepseek"):
            raise RuntimeError("simulated failure filing deepseek")
        return real_append(project_root, **kwargs)

    monkeypatch.setattr(triage, "append_triage_item_idempotent", _flaky_append)

    file_partial_degradation_triage(
        tmp_path, "run-1", "iterate", "openrouter", ["deepseek", "openai"],
    )

    assert calls == ["openrouter:deepseek", "openrouter:openai"]
    items = list(read_all_items(tmp_path))
    assert len(items) == 1
    assert items[0]["dedupKey"] == "openrouter:openai"


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in (
        "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
        "SHIPWRIGHT_REVIEW_MODEL_CHATGPT",
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_DEEPSEEK",
        "SHIPWRIGHT_REVIEW_MODEL_OPENROUTER_CHATGPT",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def fake_iterate_project(tmp_path):
    plugin_root = tmp_path / "fake-plan"
    (plugin_root / "prompts" / "plan_reviewer").mkdir(parents=True)
    (plugin_root / "prompts" / "plan_reviewer" / "system").write_text("sys", encoding="utf-8")
    (plugin_root / "prompts" / "plan_reviewer" / "user").write_text(
        "u {SPEC} {PLAN}", encoding="utf-8"
    )
    spec = tmp_path / "spec.md"
    plan = tmp_path / "plan.md"
    spec.write_text("# Spec\nDo X.", encoding="utf-8")
    plan.write_text("# Plan\nStep 1.", encoding="utf-8")
    return plugin_root, spec, plan


def _run_main_openrouter(monkeypatch, project, run_id=None):
    plugin_root, spec, plan = project
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    import external_review

    monkeypatch.setattr(
        external_review, "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(
        external_review, "review_with_openrouter",
        lambda *a, **k: (
            {"status": "degraded", "reason": "provider returned an empty reply", "via": "openrouter"}
            if a[-1] == "deepseek"
            else {"status": "success", "feedback": "looks fine", "via": "openrouter"}
        ),
    )
    argv = [
        "external_review.py", "--mode", "iterate",
        "--spec-file", str(spec), "--plan-file", str(plan),
        "--plugin-root", str(plugin_root), "--project-root", str(spec.parent),
    ]
    if run_id:
        argv += ["--run-id", run_id]
    monkeypatch.setattr("sys.argv", argv)
    return external_review.main()


def test_a_degraded_leg_files_a_triage_card(monkeypatch, clean_env, capsys, fake_iterate_project):
    project_root = fake_iterate_project[1].parent
    rc = _run_main_openrouter(monkeypatch, fake_iterate_project, run_id="iterate-test-run")

    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["partially_degraded"] is True

    items = list(read_all_items(project_root))
    assert len(items) == 1
    item = items[0]
    assert item["source"] == "external_review_degradation"
    assert "deepseek" in item["title"]
    assert item["runId"] == "iterate-test-run"
    # SENSITIVITY (triage.py CONSTITUTION rule): neutral, no file:line/secrets.
    assert ".py:" not in item["title"] and ".py:" not in item["detail"]


def test_filing_is_idempotent_within_the_dedup_window(monkeypatch, clean_env, capsys, fake_iterate_project):
    """A run of repeated failures must not spam one card per invocation."""
    project_root = fake_iterate_project[1].parent
    _run_main_openrouter(monkeypatch, fake_iterate_project, run_id="run-1")
    capsys.readouterr()
    _run_main_openrouter(monkeypatch, fake_iterate_project, run_id="run-2")
    capsys.readouterr()

    items = list(read_all_items(project_root))
    assert len(items) == 1  # second call deduped against the first


def test_no_triage_card_when_both_legs_succeed(monkeypatch, clean_env, capsys, fake_iterate_project):
    plugin_root, spec, plan = fake_iterate_project
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    import external_review

    monkeypatch.setattr(
        external_review, "load_iterate_review_prompts",
        lambda prompts_root=None: ("sys", "u {SPEC} {PLAN}"),
    )
    monkeypatch.setattr(
        external_review, "review_with_openrouter",
        lambda *a, **k: {"status": "success", "feedback": "ok", "via": "openrouter"},
    )
    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py", "--mode", "iterate",
         "--spec-file", str(spec), "--plan-file", str(plan),
         "--plugin-root", str(plugin_root), "--project-root", str(spec.parent)],
    )
    external_review.main()
    capsys.readouterr()

    assert list(read_all_items(spec.parent)) == []


def test_triage_filing_failure_never_breaks_the_review_gate(monkeypatch, clean_env, capsys, fake_iterate_project):
    """Best-effort: a broken triage write must not affect the gate's own
    exit code or stdout JSON contract."""
    import triage

    monkeypatch.setattr(
        triage, "append_triage_item_idempotent",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk full")),
    )
    rc = _run_main_openrouter(monkeypatch, fake_iterate_project, run_id="iterate-test-run")
    out = capsys.readouterr()
    payload = json.loads(out.out)

    assert rc == 0
    assert payload["success"] is True
    assert payload["partially_degraded"] is True
    assert "disk full" in out.err  # surfaced, but non-fatal
