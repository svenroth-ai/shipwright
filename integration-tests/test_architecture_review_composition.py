"""Do the architecture pass's three pieces actually compose?

The pass is spread over three components that are each covered in isolation:
the CLI emits an envelope, the recorder reads an envelope and writes a row, and
the F11 gate reads rows. Every unit test can pass while the seam between them
is broken — a `--from external-review-json` adapter that rejects this mode's
envelope, or a row shape the gate refuses — and the failure would surface only
on a live medium+ run, after the work is built.

So this walks the real chain end to end:

    brief file → external_review.py --mode architecture → envelope
              → build_review_evidence('external-review-json')
              → itemized findings the agent writes into the spec section

and pins the one property that makes the pass worth having at all: the BRIEF,
not the plan, is what reached the model.

Run in-process with the provider function replaced, deliberately. A subprocess
stub would have to be injected through ``sitecustomize``, which patches a second
module object while the CLI runs as ``__main__`` — the patch silently misses and
the test makes a real network call to a provider with a junk key. Measured while
writing this file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED_SCRIPTS = REPO_ROOT / "shared" / "scripts"
for _p in (SHARED_SCRIPTS, SHARED_SCRIPTS / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import external_review  # noqa: E402
import record_review_pass  # noqa: E402
from lib.review_findings import PARSE_STRUCTURED  # noqa: E402
from lib.review_payloads import build_review_evidence  # noqa: E402
from lib.review_record import entry_for, pending_types, read_record  # noqa: E402

RUN_ID = "iterate-2026-08-06-compose-check"

#: Written in the EXACT shape the shipped prompt mandates — `Category:` /
#: `Severity:` / `Finding:` / `Suggestion:`, one per line. Not a stylistic
#: choice: the point of this fixture is to prove prompt-shape → parsed finding →
#: recorded row. An earlier version used a category-less lowercase layout, which
#: parsed fine and therefore proved nothing about the shape the prompt actually
#: asks for — the very gap that shipped a pass recording 0 of 5 findings
#: (`parse_status: unstructured`) on its first live run.
_REPLY = """\
1. No — an existing mechanism already covers this.
2. Smallest thing: call the function directly.
3. Costs: one more workflow to keep green forever.
4. Forecloses: moving the step off CI later.

5. Findings

- Category: simpler-alternative
  Severity: high
  Finding: the queue buys an ordering guarantee nothing needs
  Suggestion: drop the queue and call the function directly

SHIPWRIGHT_VERDICT: reject
"""


@pytest.fixture
def project(tmp_path):
    run_dir = tmp_path / ".shipwright" / "planning" / "iterate" / RUN_ID
    run_dir.mkdir(parents=True)
    spec = tmp_path / "spec.md"
    brief = run_dir / "architecture_brief.md"
    spec.write_text("# Spec\nShip a thing.", encoding="utf-8")
    brief.write_text(
        "# Architecture Brief\n\n## The problem\nRuns go red unnoticed.\n\n"
        "## Options on the table\n- A: do nothing\n- B: a scheduled job\n",
        encoding="utf-8",
    )
    return tmp_path, spec, brief


@pytest.fixture
def stub_provider(monkeypatch):
    """Replace the OpenRouter leg; keep every other code path real.

    Prompt loading, the two-arm ThreadPoolExecutor, envelope assembly and
    verdict parsing all still run — only the HTTP call is gone.
    """
    seen: list[dict] = []

    def _fake(plan, spec, system_prompt, user_prompt, config, model_key):
        seen.append({
            "primary": plan,
            "system": system_prompt,
            "rendered": external_review._render_user_prompt(user_prompt, plan, spec),
            "model_key": model_key,
        })
        return {"status": "success", "feedback": _REPLY}

    monkeypatch.setattr(external_review, "review_with_openrouter", _fake)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-stub")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return seen


def _invoke(monkeypatch, argv: list[str]) -> int:
    """``external_review.main`` reads ``sys.argv`` directly (unlike
    ``record_review_pass.main``, which takes argv). Set it rather than widen a
    production signature for a test."""
    monkeypatch.setattr(sys, "argv", ["external_review.py", *argv])
    return external_review.main()


def _run_cli(monkeypatch, argv: list[str], capsys) -> dict:
    code = _invoke(monkeypatch, argv)
    out = capsys.readouterr().out
    assert code == 0, out
    return json.loads(out)


def test_the_brief_is_what_reaches_the_model(project, stub_provider, capsys, monkeypatch):
    """The substantive property. If the plan ever gets substituted here the
    pass still 'works', emits an identical envelope, and is worthless."""
    proj, spec, brief = project
    _run_cli(monkeypatch, ["--mode", "architecture", "--spec-file", str(spec),
                           "--brief-file", str(brief), "--plugin-root", str(proj),
                           "--project-root", str(proj)], capsys)

    assert len(stub_provider) == 2, "both reviewer arms must be asked"
    for call in stub_provider:
        assert "Options on the table" in call["primary"]
        assert "{BRIEF}" not in call["rendered"], "placeholder left unsubstituted"
        assert "Options on the table" in call["rendered"]
        assert "Ship a thing" in call["rendered"], "{SPEC} must render too"
        # The system prompt must be the architecture one, not iterate's.
        assert "standing mechanism" in call["system"].lower()
    assert {c["model_key"] for c in stub_provider} == {"glm", "openai"}


def test_the_envelope_is_itemizable_into_findings(project, stub_provider, capsys, monkeypatch):
    """The seam that actually exists: envelope → parsed findings.

    An earlier version of this test recorded the architecture envelope into the
    `plan` review row and asserted the row came back with findings. That
    composition is unreachable at runtime — Step 3.5 records that row from the
    FIRST call's envelope, and a completed row is immutable — so the test
    green-lit a sequence the skill never performs and could not fail for the one
    it does (Stage-3 doubt review, high). The row is not this pass's
    destination; the iterate spec's `## Architecture Review` section is.

    What still has to compose is that the reviewers' prose, written in the shape
    the shipped prompt mandates, survives the same adapter the recorder uses —
    otherwise the agent has an envelope it cannot itemize into that section.
    """
    proj, spec, brief = project
    envelope = _run_cli(monkeypatch, ["--mode", "architecture", "--spec-file", str(spec),
                                      "--brief-file", str(brief), "--plugin-root", str(proj),
                                      "--project-root", str(proj)], capsys)

    assert envelope["verdicts"] == {"glm": "reject", "openai": "reject"}
    assert envelope["contradiction"]["detected"] is False

    payload = proj / "envelope.json"
    payload.write_text(json.dumps(envelope), encoding="utf-8")

    findings, parse_status, raw, verdicts = build_review_evidence(
        "external-review-json", str(payload))

    assert parse_status == PARSE_STRUCTURED, (
        "both legs must itemize — an `unstructured` parse is how this pass "
        "shipped its first live run recording 0 of 5 findings"
    )
    assert len(findings) == 2, "one finding per reviewer leg"
    assert {f["severity"] for f in findings} == {"high"}
    assert all("queue" in f["finding"] for f in findings)
    assert verdicts == {"glm": "reject", "openai": "reject"}
    assert raw


def test_the_plan_row_is_not_this_passs_destination(
    project, stub_provider, capsys, monkeypatch
):
    """Pins the reason, so the earlier mistake cannot quietly return.

    `record_review_pass` takes ONE `--payload-file` per row and refuses to
    overwrite a terminal status. Once Step 3.5's first call has closed `plan`,
    a second write for the architecture envelope is an error, not an append.
    """
    proj, spec, brief = project
    assert record_review_pass.main(
        ["init", "--project-root", str(proj), "--run-id", RUN_ID]) == 0
    capsys.readouterr()

    # A REAL envelope, standing in for Step 3.5's first call.
    envelope = _run_cli(monkeypatch, ["--mode", "architecture", "--spec-file", str(spec),
                                      "--brief-file", str(brief), "--plugin-root", str(proj),
                                      "--project-root", str(proj)], capsys)
    payload = proj / "first.json"
    payload.write_text(json.dumps(envelope), encoding="utf-8")

    def _record(path):
        return record_review_pass.main([
            "record", "--project-root", str(proj), "--run-id", RUN_ID,
            "--review-type", "plan", "--status", "completed",
            "--from", "external-review-json", "--payload-file", str(path),
            "--provider", "openrouter", "--marker-status", "completed"])

    assert _record(payload) == 0, capsys.readouterr().out
    capsys.readouterr()

    # Now the SECOND call's envelope — different findings, same row.
    second = json.loads(json.dumps(envelope))
    for leg in second["reviews"].values():
        leg["feedback"] = leg["feedback"].replace(
            "the queue buys an ordering guarantee nothing needs",
            "ARCHITECTURE-ONLY FINDING that must not be lost")
    second_payload = proj / "second.json"
    second_payload.write_text(json.dumps(second), encoding="utf-8")

    # It does NOT error. Because the requested status equals the recorded one,
    # the CLI treats it as a marker repair and returns success with
    # `record_unchanged: true` — so the architecture findings are silently
    # DISCARDED rather than rejected. That is worse than a hard failure, and it
    # is exactly why this pass's destination is the spec section, not this row.
    assert _record(second_payload) == 0
    assert '"record_unchanged": true' in capsys.readouterr().out

    entry = entry_for(read_record(proj, RUN_ID), "plan")
    assert entry["status"] == "completed"
    assert "plan" not in pending_types(read_record(proj, RUN_ID))
    recorded = " ".join(f["finding"] for f in entry["findings"])
    assert "ARCHITECTURE-ONLY FINDING" not in recorded, (
        "the second envelope's findings never reach the row — if this ever "
        "starts passing content through, revisit where the pass records"
    )




def test_plan_file_is_refused_in_architecture_mode(project, capsys, monkeypatch):
    """The structural half of the anti-anchoring guarantee: prose can drift,
    a usage error cannot."""
    proj, spec, brief = project
    with pytest.raises(SystemExit) as exc:
        _invoke(monkeypatch, ["--mode", "architecture", "--spec-file", str(spec),
                              "--brief-file", str(brief), "--plan-file", str(brief),
                              "--plugin-root", str(proj)])
    assert exc.value.code == 2
    assert "--plan-file belongs to --mode plan" in capsys.readouterr().err
