"""Independent AI gap check: reply parsing, the PR-body block, diff trimming, the never-blocks promise, the F11 record check."""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

from lib.ai_gap_check_core import (
    SYSTEM_PROMPT,
    USER_TEMPLATE,
    catalog_from_specs,
    declaration_from_event,
    owning_frs,
    parse_reply,
    render_block,
    render_not_run,
    render_spec_context,
    trim_diff,
)
from tools import ai_gap_check as tool
from tools.verifiers import _finalization_claims as claims
from tools.verifiers.ai_gap_check_record import CHECK_NAME, check_ai_gap_check_recorded

_RUN = "iterate-2026-10-31-gap-probe"
_AC = "FR-01.11/AC49"
_GOOD = {
    "requirements_changed": [{"ac": "FR-01.11.AC03", "why": "now also covers fixes"}],
    "requirements_checked": [{"ac": "FR-01.11.AC47", "why": "still holds"}],
    "verdict": "disagree", "gap": True, "gap_fr": "FR-01.11", "reason": "New behaviour no criterion describes.",
}


@pytest.mark.covers("FR-01.11", _AC)
def test_parse_reply_accepts_plain_and_fenced_json():
    assert parse_reply(json.dumps(_GOOD))["verdict"] == "disagree"
    fenced = "Here you go:\n```json\n" + json.dumps(_GOOD) + "\n```\n"
    out = parse_reply(fenced)
    assert out["gap"] is True and out["requirements_changed"][0]["ac"] == "FR-01.11.AC03"
    assert parse_reply("noise " + json.dumps(_GOOD) + " trailing")["gap_fr"] == "FR-01.11"


@pytest.mark.covers("FR-01.11", _AC)
@pytest.mark.parametrize("bad", ["", "no json here", '{"verdict": "maybe", "gap": true}', '{"verdict": "agree"}', '{"verdict": "agree", "gap": "yes"}', "[1, 2]"])
def test_parse_reply_rejects_unusable_replies(bad):
    with pytest.raises(ValueError):
        parse_reply(bad)


@pytest.mark.covers("FR-01.11", _AC)
def test_block_has_the_four_parts_and_says_it_is_advisory():
    block = render_block(parse_reply(json.dumps(_GOOD)), "some/model")
    for part in ("Requirements changed: FR-01.11.AC03", "Requirements checked: FR-01.11.AC47", "**disagree**", "Catalog gap: **yes (nearest FR-01.11)**"):
        assert part in block
    assert "never blocks" in block
    assert "Catalog gap: **no**" in render_block(parse_reply(json.dumps({**_GOOD, "gap": False, "gap_fr": ""})))


@pytest.mark.covers("FR-01.11", _AC)
def test_not_run_note_is_visible_and_says_nothing_was_blocked():
    note = render_not_run("no key\nset   anywhere")
    assert note.startswith("### Independent gap check") and "Not run: no key set anywhere" in note and "Nothing was blocked" in note


@pytest.mark.covers("FR-01.11", _AC)
def test_declaration_and_owning_frs():
    event = {"type": "work_completed", "intent": "change", "summary": "s", "spec_impact": "none", "affected_frs": ["FR-01.03"],
             "affected_acs": [{"ac": "FR-01.11.AC47", "disposition": "x", "why": "y"}], "catalog_gap": True, "catalog_gap_fr": "FR-01.05",
             "changed_files": ["a"], "empty": ""}
    decl = declaration_from_event(event)
    assert "changed_files" not in decl and "type" not in decl and "empty" not in decl
    assert set(owning_frs(decl)) == {"FR-01.03", "FR-01.05", "FR-01.11"}
    assert declaration_from_event(None) == {} and owning_frs({}) == []
    assert "(no declaration was recorded)" in render_spec_context({}, "cat")


@pytest.mark.covers("FR-01.11", _AC)
def test_catalog_takes_the_criteria_section_only():
    spec = "# S\n## Functional Requirements\ntable\n## Acceptance Criteria\n### FR-01.01 - x\n- AC\n## Provenance\nrun log\n"
    cat = catalog_from_specs([spec, "plain spec without the section"])
    assert "### FR-01.01" in cat and "table" not in cat and "run log" not in cat and "plain spec without the section" in cat


@pytest.mark.covers("FR-01.11", _AC)
def test_trim_drops_finalization_records_and_cuts_by_whole_file():
    def chunk(path: str, body: str = "+x\n") -> str:
        return f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n{body}"

    diff = "".join([chunk("shared/scripts/lib/a.py"), chunk("shipwright_events.jsonl"), chunk("CHANGELOG-unreleased.d/Added/x.md"),
                    chunk(".shipwright/planning/iterate/run-1/external-code-review-raw.json"), chunk(".shipwright/planning/iterate/run-1/mini-plan.md")])
    text, dropped, cut = trim_diff(diff)
    assert "lib/a.py" in text and "mini-plan.md" in text and "events.jsonl" not in text
    assert len(dropped) == 3 and cut == []
    big = chunk("big1.py", "+" + "y" * 50 + "\n") + chunk("big2.py", "+" + "z" * 50 + "\n")
    text, _, cut = trim_diff(big, max_chars=150)
    assert "big1.py" in text and cut == ["big2.py"] and "left out because the diff was too large: big2.py" in text


@pytest.mark.covers("FR-01.11", _AC)
def test_prompt_frames_a_gap_check_not_an_untrue_detector():
    assert 'wrong "none"' in SYSTEM_PROMPT and "catalog gap" in SYSTEM_PROMPT
    assert "{SPEC}" in USER_TEMPLATE and "{DIFF}" in USER_TEMPLATE


def _fake_review(monkeypatch, reply: dict) -> dict:
    seen: dict = {}
    mod = types.ModuleType("external_review")

    def review_with_openrouter(primary, spec, system_prompt, user_prompt, config, model_key):
        seen.update(primary=primary, spec=spec, key=model_key)
        return reply

    mod.review_with_openrouter = review_with_openrouter  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "external_review", mod)
    import external_review_config as cfg
    import external_review_gateway as gw

    monkeypatch.setattr(cfg, "is_external_review_enabled", lambda c: True)
    monkeypatch.setattr(cfg, "is_external_code_review_enabled", lambda c: True)
    monkeypatch.setattr(gw, "gateway_configured", lambda: False)
    return seen


_DIFF = "diff --git a/shared/scripts/lib/a.py b/shared/scripts/lib/a.py\n--- a/shared/scripts/lib/a.py\n+++ b/shared/scripts/lib/a.py\n@@ -0,0 +1 @@\n+x\n"
_SPEC = "## Acceptance Criteria\n### FR-01.11 - x\n- (E) [AC01] Given a, when b, then c.\n"


@pytest.mark.covers("FR-01.11", _AC)
def test_run_check_ran_passes_free_text_through_arguments(monkeypatch, tmp_path):
    seen = _fake_review(monkeypatch, {"status": "success", "feedback": json.dumps(_GOOD)})
    rec = tool.run_check(_DIFF, {"summary": "$(touch pwned) `x`"}, [_SPEC], "openai", tmp_path)
    assert rec["status"] == "ran" and rec["result"]["verdict"] == "disagree" and seen["key"] == "openai"
    assert "$(touch pwned)" in seen["spec"] and "FR-01.11" in seen["spec"] and "a.py" in seen["primary"]
    assert "Independent gap check" in tool.block_for(rec)


@pytest.mark.covers("FR-01.11", _AC)
@pytest.mark.parametrize("reply", [
    {"status": "skipped", "reason": "No OPENROUTER_API_KEY set"},
    {"status": "error", "reason": "provider down"},
    {"status": "degraded", "reason": "empty reply"},
    {"status": "success", "feedback": "not json at all"},
])
def test_run_check_degrades_to_not_run_never_raises(monkeypatch, tmp_path, reply):
    _fake_review(monkeypatch, reply)
    rec = tool.run_check(_DIFF, {}, [_SPEC], "openai", tmp_path)
    assert rec["status"] == "not_run" and rec["reason"]
    assert tool.block_for(rec).startswith("### Independent gap check") and "Not run" in tool.block_for(rec)


@pytest.mark.covers("FR-01.11", _AC)
def test_run_check_without_diff_or_catalog_is_not_run(tmp_path):
    assert tool.run_check("", {}, [_SPEC], "openai", tmp_path)["status"] == "not_run"
    assert "catalog" in tool.run_check(_DIFF, {}, [], "openai", tmp_path)["reason"]


@pytest.mark.covers("FR-01.11", _AC)
def test_run_check_survives_a_crashing_provider_module(monkeypatch, tmp_path):
    mod = types.ModuleType("external_review")

    def boom(*a, **k):
        raise RuntimeError("network exploded")

    mod.review_with_openrouter = boom  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "external_review", mod)
    rec = tool.run_check(_DIFF, {}, [_SPEC], "openai", tmp_path)
    assert rec["status"] == "not_run" and "network exploded" in rec["reason"]


@pytest.mark.covers("FR-01.11", _AC)
def test_main_always_exits_zero_and_writes_both_files(monkeypatch, tmp_path):
    _fake_review(monkeypatch, {"status": "error", "reason": "provider down"})
    diff, out = tmp_path / "d.diff", tmp_path / "out"
    diff.write_text(_DIFF, encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text(_SPEC, encoding="utf-8")
    event = tmp_path / "e.json"
    event.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", "--project-root", str(tmp_path), "--run-id", _RUN, "--diff-file", str(diff),
                                      "--spec-file", str(spec), "--event-file", str(event), "--out-dir", str(out)])
    assert tool.main() == 0
    record = json.loads((out / "ai-gap-check.json").read_text(encoding="utf-8"))
    assert record["status"] == "not_run" and (out / "ai-gap-check.md").read_text(encoding="utf-8").startswith("### Independent gap check")
    monkeypatch.setattr(sys, "argv", ["x", "--project-root", str(tmp_path), "--diff-file", str(tmp_path / "missing.diff"), "--out-dir", str(out)])
    assert tool.main() == 0  # an unreadable input is a not_run note too
    assert json.loads((out / "ai-gap-check.json").read_text(encoding="utf-8"))["status"] == "not_run"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


@pytest.mark.covers("FR-01.11", _AC)
def test_working_tree_diff_sees_committed_edited_and_new_files(tmp_path):
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@example.org")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "a.txt").write_text("one\n", encoding="utf-8")
    _git(tmp_path, "add", "a.txt")
    _git(tmp_path, "commit", "-q", "-m", "base")
    _git(tmp_path, "checkout", "-q", "-b", "work")
    (tmp_path / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    (tmp_path / "new.txt").write_text("brand new\n", encoding="utf-8")
    diff = tool.working_tree_diff(tmp_path, "main")
    assert "+two" in diff and "+brand new" in diff and "new.txt" in diff
    assert "new.txt" not in _git(tmp_path, "diff", "--cached", "--name-only")  # the index stays untouched


def _event(tmp_path: Path, **kw) -> None:
    evt = {"type": "work_completed", "source": "iterate", "adr_id": _RUN, "intent": "change", **kw}
    (tmp_path / "shipwright_events.jsonl").write_text(json.dumps(evt) + "\n", encoding="utf-8")


@pytest.mark.covers("FR-01.11", _AC)
def test_record_check_is_advisory_and_accepts_ran_or_not_run(tmp_path):
    assert check_ai_gap_check_recorded(tmp_path, _RUN).severity == "skipped"  # no event
    _event(tmp_path, source="adopt")
    assert check_ai_gap_check_recorded(tmp_path, _RUN).severity == "skipped"
    _event(tmp_path)
    missing = check_ai_gap_check_recorded(tmp_path, _RUN)
    assert missing.ok is False and missing.severity == "warning" and missing.strict_exempt
    run_dir = tmp_path / ".shipwright" / "planning" / "iterate" / _RUN
    run_dir.mkdir(parents=True)
    rec = run_dir / "ai-gap-check.json"
    for status in ("ran", "not_run"):
        rec.write_text(json.dumps({"status": status}), encoding="utf-8")
        assert check_ai_gap_check_recorded(tmp_path, _RUN).ok
    for bad in ("{broken", json.dumps({"status": "weird"}), "[]"):
        rec.write_text(bad, encoding="utf-8")
        res = check_ai_gap_check_recorded(tmp_path, _RUN)
        assert res.ok is False and res.severity == "warning" and res.strict_exempt


@pytest.mark.covers("FR-01.11", _AC)
def test_record_check_is_registered():
    assert check_ai_gap_check_recorded in claims.CLAIM_CHECKS and CHECK_NAME


@pytest.mark.covers("FR-01.11", _AC)
def test_block_renders_model_text_inert_and_flags_an_incomplete_input():
    nasty = {**_GOOD, "reason": "ping @someone <img src=x> [click](http://e) `rm` | table", "requirements_changed": [{"ac": "FR-01.11.AC03", "why": "**bold** @bob"}]}
    block = render_block(parse_reply(json.dumps(nasty)), "m", ["big.py"])
    assert "@someone" not in block and "@bob" not in block  # a zero-width character follows every @
    assert "<img" not in block and "[click]" not in block and "`rm`" not in block and "**bold**" not in block
    assert "Incomplete input: 1 file(s) were left out" in block
    assert "Incomplete input" not in render_block(parse_reply(json.dumps(_GOOD)), "m")


@pytest.mark.covers("FR-01.11", _AC)
def test_run_check_refuses_a_claude_family_model(monkeypatch, tmp_path):
    _fake_review(monkeypatch, {"status": "success", "feedback": json.dumps(_GOOD)})
    import external_review_routing as routing

    monkeypatch.setattr(routing, "resolve_reviewer_model", lambda *a, **k: "anthropic/claude-opus-5-5")
    rec = tool.run_check(_DIFF, {}, [_SPEC], "openai", tmp_path)
    assert rec["status"] == "not_run" and "not independent" in rec["reason"]


@pytest.mark.covers("FR-01.11", _AC)
def test_incomplete_reply_is_unusable_and_first_oversized_file_is_cut():
    with pytest.raises(ValueError):
        parse_reply('{"verdict": "agree", "gap": false}')
    with pytest.raises(ValueError):
        parse_reply(json.dumps({**_GOOD, "reason": " "}))
    head = "diff --git a/{p} b/{p}\n--- a/{p}\n+++ b/{p}\n@@ -0,0 +1 @@\n"
    big = head.format(p="gen.py") + "+" + "q" * 500 + "\n"
    small = head.format(p="ok.py") + "+x\n"
    text, _, cut = trim_diff(big + small, max_chars=300)
    assert cut == ["gen.py"] and "ok.py" in text and "qqqq" not in text


@pytest.mark.covers("FR-01.11", _AC)
def test_not_run_note_is_inert():
    note = render_not_run("error: <script> @everyone [x](y)")
    assert "<script>" not in note and "@everyone" not in note and "[x]" not in note


@pytest.mark.covers("FR-01.11", _AC)
def test_replay_reads_the_event_the_pr_added():
    from tools.ai_gap_check_replay import event_in_diff

    evt = {"type": "work_completed", "source": "iterate", "spec_impact": "none"}
    other = {"type": "grade_snapshot"}
    diff = ("diff --git a/other.py b/other.py\n+" + json.dumps(evt) + "\n"
            "diff --git a/shipwright_events.jsonl b/shipwright_events.jsonl\n--- a/shipwright_events.jsonl\n+++ b/shipwright_events.jsonl\n"
            "+" + json.dumps(other) + "\n+" + json.dumps(evt) + "\n")
    assert event_in_diff(diff) == evt
    assert event_in_diff("diff --git a/x b/x\n+" + json.dumps(evt)) == {}


@pytest.mark.covers("FR-01.11", _AC)
def test_run_check_respects_opt_outs_and_gateway(monkeypatch, tmp_path):
    import external_review_config as cfg
    import external_review_gateway as gw

    seen = _fake_review(monkeypatch, {"status": "success", "feedback": json.dumps(_GOOD)})
    monkeypatch.setattr(cfg, "is_external_code_review_enabled", lambda c: False)
    rec = tool.run_check(_DIFF, {}, [_SPEC], "openai", tmp_path)
    assert rec["status"] == "not_run" and "switched off" in rec["reason"] and not seen
    monkeypatch.setattr(cfg, "is_external_code_review_enabled", lambda c: True)
    monkeypatch.setattr(gw, "gateway_configured", lambda: True)
    rec = tool.run_check(_DIFF, {}, [_SPEC], "openai", tmp_path)
    assert rec["status"] == "not_run" and "gateway" in rec["reason"] and not seen


@pytest.mark.covers("FR-01.11", _AC)
def test_codex_driver_never_gets_a_gpt_reviewer_and_secret_files_stay_home(monkeypatch, tmp_path):
    seen = _fake_review(monkeypatch, {"status": "success", "feedback": json.dumps(_GOOD)})
    diff, out, spec = tmp_path / "d.diff", tmp_path / "out", tmp_path / "s.md"
    diff.write_text(_DIFF, encoding="utf-8")
    spec.write_text(_SPEC, encoding="utf-8")
    ev = tmp_path / "e.json"
    ev.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["x", "--project-root", str(tmp_path), "--diff-file", str(diff), "--spec-file", str(spec),
                                      "--event-file", str(ev), "--out-dir", str(out), "--driver", "codex"])
    assert tool.main() == 0 and seen["key"] == "glm"
    for name, hidden in (("notes.env", False), (".env.local", True), ("server.pem", True), ("my_credentials.json", True), ("a.py", False)):
        assert bool(tool._SECRET_SHAPED.search(name)) is hidden
    from lib.ai_gap_check_core import trim_diff as trim
    gap = "diff --git a/x b/.shipwright/planning/iterate/r/ai-gap-check.json\n+old verdict\n"
    assert "old verdict" not in trim(gap)[0]
