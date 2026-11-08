"""Q2 phase 1 follow-up: the AC claims reach the spec-reviewer on EVERY review path, not only the standalone Step 8.

Two paths used to omit the claims file and so always printed "no AC review ran": the campaign sub-iterate-runner /
3f-bis cascade and the Codex-CLI dispatch. Hermetic: the Codex child process is a stub, the docs are read as text.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parent))

_SHARED = Path(__file__).resolve().parents[1]
_REPO = _SHARED.parent
sys.path.insert(0, str(_SHARED / "scripts"))

from _review_cli_harness import RUN_ID, make_project, payload, run_tool  # noqa: E402
from lib import codex_review_transport as transport  # noqa: E402
from lib.review_payloads import CANONICAL_PAYLOAD_BASENAMES  # noqa: E402
from lib.review_record import read_record  # noqa: E402
from tools import review_via_codex  # noqa: E402

_REFS = _REPO / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "references"
_ROW = {"ac": "FR-01.03.AC06", "verdict": "diverges", "diff_location": "src/save.ts:41", "reason": "second save overwrites", "weakens": None}
_BASE = {"stage": "spec-compliance", "verdict": "PASS", "spec_citations": [], "summary": "ok"}
_BUILD = 'ac_claims.py" build'


def _flat(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


# --- Codex schema ---------------------------------------------------------------------------------------------------

def _validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(transport.ROLE_SCHEMAS["spec"].read_text(encoding="utf-8")))


@pytest.mark.covers("FR-01.11/AC50")
@pytest.mark.parametrize("ac_verdicts", [None, [], [_ROW], [{**_ROW, "verdict": "matches", "diff_location": None, "weakens": True}]])
def test_the_codex_spec_schema_takes_null_or_per_ac_rows(ac_verdicts):
    assert not list(_validator().iter_errors({**_BASE, "ac_verdicts": ac_verdicts}))


@pytest.mark.covers("FR-01.11/AC50")
def test_the_codex_spec_schema_requires_the_key_and_closes_the_row_shape():
    v = _validator()
    assert list(v.iter_errors(_BASE)), "strict mode: the nullable key must be listed in required"
    assert list(v.iter_errors({**_BASE, "ac_verdicts": [{**_ROW, "verdict": "maybe"}]}))
    assert list(v.iter_errors({**_BASE, "ac_verdicts": [{**_ROW, "extra": 1}]}))


# --- review_via_codex.py --claims-file --------------------------------------------------------------------------------

def _dispatch(tmp_path, monkeypatch, role, reply, *extra):
    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (True, ""))
    monkeypatch.setattr(transport, "_resolve_codex_binary", lambda: "codex")
    seen = {}

    def _run(argv, input=None, **kw):  # noqa: A002
        if argv[0] != "codex":  # the main-root resolver's git call
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="not a git repo")
        seen["prompt"] = input
        Path(argv[argv.index("-o") + 1]).write_text(json.dumps(reply), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(transport.subprocess, "run", _run)
    files = {n: tmp_path / n for n in ("agent.md", "spec.md", "the.diff")}
    for name, f in files.items():
        f.write_text(f"content of {name}", encoding="utf-8")
    argv = ["--role", role, "--worktree-root", str(tmp_path), "--agent-md", str(files["agent.md"]), "--out-dir", str(tmp_path / "out"),
            "--spec-file", str(files["spec.md"]), "--diff-file", str(files["the.diff"]), *extra]
    return review_via_codex.main(argv), seen.get("prompt", "")


@pytest.mark.covers("FR-01.11/AC50")
def test_a_spec_pass_with_a_claims_file_puts_it_in_the_prompt(tmp_path, monkeypatch, capsys):
    claims = tmp_path / "ac-claims.json"
    claims.write_text('{"claims": [{"ac": "FR-01.03.AC06"}]}', encoding="utf-8")
    code, prompt = _dispatch(tmp_path, monkeypatch, "spec", {**_BASE, "ac_verdicts": [_ROW]}, "--claims-file", str(claims))
    assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "completed"
    assert "FR-01.03.AC06" in prompt and "AC claims file" in prompt and "No AC claims file was passed" not in prompt


@pytest.mark.covers("FR-01.11/AC50")
def test_a_spec_pass_without_claims_is_told_to_answer_null(tmp_path, monkeypatch, capsys):
    code, prompt = _dispatch(tmp_path, monkeypatch, "spec", {**_BASE, "ac_verdicts": None})
    assert code == 0 and json.loads(capsys.readouterr().out)["status"] == "completed"
    assert "No AC claims file was passed" in prompt and "`ac_verdicts` to null" in prompt


@pytest.mark.covers("FR-01.11/AC50")
def test_a_claims_file_is_refused_for_every_other_role_and_when_unreadable(tmp_path, monkeypatch, capsys):
    claims = tmp_path / "ac-claims.json"
    claims.write_text("{}", encoding="utf-8")
    code, prompt = _dispatch(tmp_path, monkeypatch, "code", {"section": "s", "review": []}, "--claims-file", str(claims))
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["status"] == "error" and "only valid for --role spec" in out["reason"] and prompt == ""
    code, _ = _dispatch(tmp_path, monkeypatch, "spec", {**_BASE, "ac_verdicts": None}, "--claims-file", str(tmp_path / "missing.json"))
    assert code == 1 and "could not read an input file" in json.loads(capsys.readouterr().out)["reason"]


# --- the Codex reply lands on the spec row exactly like the Agent-tool reply ---------------------------------------------

def _record(tmp_path, reply):
    project = make_project(tmp_path)
    run_tool(project, "init")
    code, out = run_tool(project, "record", "--review-type", "spec", "--status", "completed", "--from", "spec-reviewer",
                         "--payload-file", payload(tmp_path, CANONICAL_PAYLOAD_BASENAMES["spec"], json.dumps(reply)),
                         "--transport", "codex", "--transport-note", "gpt effort=high sandbox=read-only")
    assert code == 0, out
    return read_record(project, RUN_ID)["reviews"]["spec"]


@pytest.mark.covers("FR-01.11/AC50")
def test_a_codex_reply_with_verdicts_carries_them_onto_the_spec_row(tmp_path):
    assert _record(tmp_path, {**_BASE, "ac_verdicts": [_ROW]})["ac_verdicts"] == [_ROW]


@pytest.mark.covers("FR-01.11/AC50")
def test_a_codex_reply_with_null_records_exactly_as_before(tmp_path):
    assert "ac_verdicts" not in _record(tmp_path, {**_BASE, "ac_verdicts": None})


# --- the procedure text: both paths build the file and hand it over --------------------------------------------------------

@pytest.mark.covers("FR-01.11/AC50")
def test_the_runner_cascade_reference_builds_and_passes_the_claims_before_the_spec_spawn():
    flat = _flat(_REFS / "campaign-step-3-7-internal-reviews.md")
    assert _BUILD in flat and "--base-ref" in flat and "{base_branch}" in flat
    assert "Also read the AC claims file" in flat and "do not commit" in flat.lower() and "claims: 0" in flat
    assert flat.index(_BUILD) < flat.index("Record the pair 3f-bis can verify")


@pytest.mark.covers("FR-01.11/AC50")
def test_the_orchestrator_cascade_builds_in_the_unit_worktree_before_stage_one():
    flat = _flat(_REFS / "campaign-mode.md")
    start = flat.index("a) `spec-reviewer`")
    block = flat[flat.rindex(_BUILD, 0, start): flat.index("b) `code-reviewer`", start)]
    assert '--project-root "$unit_wt"' in block and "origin/{default}" in block and "ac-claims.json" in block
    assert "claims: 0" in block and "Also read the AC claims file" in block


@pytest.mark.covers("FR-01.11/AC50")
def test_the_codex_dispatch_builds_the_claims_and_passes_the_flag():
    flat = _flat(_SHARED / "prompts" / "codex_review_dispatch.md")
    assert _BUILD in flat and "--claims-file" in flat and "ac_verdicts" in flat and "claims: 0" in flat


@pytest.mark.covers("FR-01.11/AC50")
def test_the_grandfathered_prompts_did_not_grow_and_the_new_ones_stay_in_the_cap():
    assert len((_REFS / "campaign-mode.md").read_text(encoding="utf-8").splitlines()) <= 1708
    assert len((_REFS / "campaign-step-3-7-internal-reviews.md").read_text(encoding="utf-8").splitlines()) <= 400
    assert len((_SHARED / "prompts" / "codex_review_dispatch.md").read_text(encoding="utf-8").splitlines()) <= 400


@pytest.mark.covers("FR-01.11/AC50")
def test_integration_codex_dispatch_to_the_recorded_spec_row(tmp_path, monkeypatch, capsys):
    """review_via_codex (stubbed child) -> its canonical reply file -> record_review_pass -> the spec row: the pieces compose."""
    claims = tmp_path / "ac-claims.json"
    claims.write_text('{"claims": [{"ac": "FR-01.03.AC06"}]}', encoding="utf-8")
    code, _ = _dispatch(tmp_path, monkeypatch, "spec", {**_BASE, "ac_verdicts": [_ROW]}, "--claims-file", str(claims))
    result = json.loads(capsys.readouterr().out)
    assert code == 0 and result["status"] == "completed"
    monkeypatch.undo()  # the stub patched subprocess.run process-wide; the recorder runs as a real child
    reply = json.loads(Path(result["canonical_path"]).read_text(encoding="utf-8"))
    assert _record(tmp_path, reply)["ac_verdicts"] == [_ROW]
