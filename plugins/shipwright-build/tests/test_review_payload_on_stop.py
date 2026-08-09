"""Tests for the review-payload-on-stop SubagentStop salvage hook.

Root cause (iterate-2026-08-09-compaction-state-audit): a review subagent's
raw reply exists only in the Task tool's result until the orchestrator's next
action writes it to a payload file for record_review_pass.py. This hook is a
synchronous, code-level fallback that salvages the reply straight from the
subagent's own transcript if the orchestrator has not recorded it by the time
the subagent stops — independent of the orchestrator's remaining context
budget, so a compaction landing in that exact window can no longer lose the
finding outright.
"""
from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = PLUGIN_ROOT / "scripts" / "hooks" / "write-review-payload-on-stop.py"


def _load_hook():
    spec = importlib.util.spec_from_file_location("write_review_payload_on_stop", HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


hook = _load_hook()

RUN_ID = "iterate-2026-08-09-compaction-state-audit"


def _transcript(tmp_path: Path, lines: list[dict]) -> str:
    p = tmp_path / "transcript.jsonl"
    p.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
    return str(p)


def _run_hook(monkeypatch, argv, payload, project_root):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    err = io.StringIO()
    monkeypatch.setattr("sys.stderr", err)
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(project_root))
    rc = hook.main(argv)
    return rc, err.getvalue()


def _write_reviews_json(project_root: Path, run_id: str, reviews: dict) -> None:
    run_dir = project_root / ".shipwright" / "planning" / "iterate" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "reviews.json").write_text(
        json.dumps({"schema_version": 1, "run_id": run_id, "reviews": reviews}, indent=2),
        encoding="utf-8",
    )


# --- salvage path ------------------------------------------------------- #

def test_salvages_reply_when_not_yet_recorded(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"Review this diff for run {RUN_ID}."},
        {"role": "assistant", "content": '```json\n{"section": "auth", "review": []}\n```'},
    ])
    rc, err = _run_hook(monkeypatch, ["--review-type", "code"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    out = hook.salvage_path(tmp_path, RUN_ID, "code")
    assert out.exists()
    assert hook.looks_like_review_payload(out.read_text(encoding="utf-8"))
    assert "salvaged" in err


def test_salvages_raw_json_reply_without_fence(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"Review this for {RUN_ID}."},
        {"role": "assistant", "content": '{"stage": "spec", "verdict": "pass", "spec_citations": []}'},
    ])
    rc, _err = _run_hook(monkeypatch, ["--review-type", "spec"],
                         {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    out = hook.salvage_path(tmp_path, RUN_ID, "spec")
    assert out.exists()
    assert json.loads(out.read_text(encoding="utf-8"))["verdict"] == "pass"


def test_content_as_block_list_is_handled(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": [{"type": "text", "text": f"run {RUN_ID}"}]},
        {"role": "assistant", "content": [{"type": "text", "text": '{"verdict": "block", "findings": []}'}]},
    ])
    rc, _err = _run_hook(monkeypatch, ["--review-type", "doubt"],
                         {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert hook.salvage_path(tmp_path, RUN_ID, "doubt").exists()


# --- no-op conditions ----------------------------------------------------- #

def test_noop_when_already_recorded(tmp_path, monkeypatch):
    _write_reviews_json(tmp_path, RUN_ID, {"code": {"status": "completed"}})
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"Review for {RUN_ID}"},
        {"role": "assistant", "content": '{"section": "x", "review": []}'},
    ])
    rc, err = _run_hook(monkeypatch, ["--review-type", "code"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert not hook.salvage_path(tmp_path, RUN_ID, "code").exists()
    assert "no-op" in err


def test_noop_when_recorded_not_run_or_not_applicable(tmp_path, monkeypatch):
    _write_reviews_json(tmp_path, RUN_ID, {"doubt": {"status": "not_applicable"}})
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"{RUN_ID}"},
        {"role": "assistant", "content": '{"verdict": "n/a"}'},
    ])
    rc, _err = _run_hook(monkeypatch, ["--review-type", "doubt"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert not hook.salvage_path(tmp_path, RUN_ID, "doubt").exists()


def test_salvages_when_pending_despite_record_existing(tmp_path, monkeypatch):
    # init already ran (all types materialized pending) — code is still pending.
    _write_reviews_json(tmp_path, RUN_ID, {"self": {"status": "completed"}, "code": {"status": "pending"}})
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"{RUN_ID}"},
        {"role": "assistant", "content": '{"section": "x", "review": [{"severity": "high"}]}'},
    ])
    rc, _err = _run_hook(monkeypatch, ["--review-type", "code"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert hook.salvage_path(tmp_path, RUN_ID, "code").exists()


def test_legacy_gates_section_spec_is_recognized(tmp_path, monkeypatch):
    # Records written before the `spec` promotion keep it under `gates`.
    run_dir = tmp_path / ".shipwright" / "planning" / "iterate" / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "reviews.json").write_text(json.dumps({
        "schema_version": 1, "run_id": RUN_ID,
        "gates": {"spec": {"status": "completed"}}, "reviews": {},
    }), encoding="utf-8")
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"{RUN_ID}"},
        {"role": "assistant", "content": '{"stage": "spec", "verdict": "pass"}'},
    ])
    rc, err = _run_hook(monkeypatch, ["--review-type", "spec"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert not hook.salvage_path(tmp_path, RUN_ID, "spec").exists()
    assert "no-op" in err


def test_salvages_when_reviews_json_is_structurally_malformed(tmp_path, monkeypatch):
    # A corrupted/incompatible reviews.json (section holds a non-dict) must
    # degrade to "not recorded" rather than raising out of already_recorded().
    run_dir = tmp_path / ".shipwright" / "planning" / "iterate" / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "reviews.json").write_text(
        json.dumps({"schema_version": 1, "run_id": RUN_ID, "reviews": "not-a-dict"}),
        encoding="utf-8",
    )
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"{RUN_ID}"},
        {"role": "assistant", "content": '{"section": "x", "review": []}'},
    ])
    rc, _err = _run_hook(monkeypatch, ["--review-type", "code"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert hook.salvage_path(tmp_path, RUN_ID, "code").exists()


def test_noop_when_no_run_id_in_transcript(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": "review this diff"},
        {"role": "assistant", "content": '{"section": "x", "review": []}'},
    ])
    rc, err = _run_hook(monkeypatch, ["--review-type", "code"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert "no run_id found" in err


def test_noop_when_reply_not_a_review_payload(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"{RUN_ID}"},
        {"role": "assistant", "content": "I could not complete the review."},
    ])
    rc, err = _run_hook(monkeypatch, ["--review-type", "code"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert "no salvageable review payload" in err
    assert not hook.salvage_path(tmp_path, RUN_ID, "code").exists()


def test_never_blocks_on_bad_stdin_payload(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("{not valid json"))
    monkeypatch.setattr("sys.stderr", io.StringIO())
    assert hook.main(["--review-type", "code"]) == 0


def test_never_blocks_on_missing_transcript_path(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"foo": "bar"})))
    monkeypatch.setattr("sys.stderr", io.StringIO())
    assert hook.main(["--review-type", "code"]) == 0


def test_never_blocks_when_salvage_write_raises(tmp_path, monkeypatch):
    transcript = _transcript(tmp_path, [
        {"role": "user", "content": f"{RUN_ID}"},
        {"role": "assistant", "content": '{"section": "x", "review": []}'},
    ])

    def _raise(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "mkdir", _raise)
    rc, err = _run_hook(monkeypatch, ["--review-type", "code"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert "could not write salvage file" in err


def test_never_blocks_on_empty_transcript(tmp_path, monkeypatch):
    transcript = str(tmp_path / "missing.jsonl")
    monkeypatch.setattr(hook, "read_transcript_with_retry", lambda *a, **k: [])
    rc, err = _run_hook(monkeypatch, ["--review-type", "code"],
                        {"transcript_path": transcript}, tmp_path)
    assert rc == 0
    assert "nothing to salvage" in err


# --- helpers directly ------------------------------------------------------ #

def test_looks_like_review_payload_rejects_prose():
    assert hook.looks_like_review_payload("just some assistant prose") is False


def test_looks_like_review_payload_accepts_fenced_and_raw():
    assert hook.looks_like_review_payload('```json\n{"a": 1}\n```') is True
    assert hook.looks_like_review_payload('{"a": 1}') is True


def test_extract_run_id_finds_first_match():
    entries = [
        {"role": "user", "content": "no id here"},
        {"role": "assistant", "content": f"working on {RUN_ID} now"},
    ]
    assert hook.extract_run_id(entries) == RUN_ID


def test_extract_run_id_none_when_absent():
    assert hook.extract_run_id([{"role": "user", "content": "nothing"}]) is None
