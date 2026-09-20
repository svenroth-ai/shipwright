"""AC2 fixture: three sequential Codex-driven review passes (spec, code,
doubt) land in `reviews.json` as genuinely distinct rows — not one
session's self-report reformatted three ways.

(`Spec/codex-plugin-execution-reliability.md` §4 AC2, quoted verbatim in
the iterate spec's "Cited Source Excerpts" section since that file is
local-only and unreachable from a fresh worktree:

    "2. The review cascade (spec-reviewer -> code-reviewer -> doubt-reviewer)
    runs as real, separate subagent invocations under Codex (via the M4
    role mapping)... A fixture proves the cascade's evidence record
    (reviews.json) shows genuinely distinct review passes, not a single
    session's self-report reformatted three ways."

Only the outermost boundary — the `codex exec` subprocess call — is
mocked, one call per role with its own distinct canned payload; the real
`run_codex_review` -> `record_review_pass.py record` -> `... show` path
runs exactly as it would end-to-end, mirroring how the existing transport
tests mock at the process boundary (`test_codex_review_transport.py`) and
how `test_record_review_pass_cli.py`'s AC8 test drives the CLI as a real
subprocess against a real evidence file, rather than mocking record_review_
pass.py itself.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))

from lib import codex_review_transport as transport  # noqa: E402

# Three DISTINCT payloads, one per role -- distinct summary/finding text so
# a regression that answered all three roles from ONE reformatted
# self-report is caught by content, not just by row count.
_SPEC_PAYLOAD = {
    "stage": "spec-compliance", "verdict": "REJECT",
    "spec_citations": [{
        "spec_ref": "AC1", "kind": "unfaithful", "diff_location": "lib/x.py:1",
        "divergence": "spec-reviewer citation: AC1 says gated on role, diff guards on model instead",
    }],
    "summary": "spec-reviewer: one AC diverges from the diff",
}
_CODE_PAYLOAD = {
    "section": "m4-codex-subagent-dispatch",
    "review": [{
        "severity": "medium", "category": "readability", "file": "lib/x.py",
        "line": 12, "finding": "code-reviewer finding: helper could be inlined",
        "suggestion": "inline the one-call helper", "source": None,
    }],
}
_DOUBT_PAYLOAD = {
    "stage": "doubt", "gating": "advisory-must-address", "trigger": "io-boundary",
    "doubts": [{
        "severity": "low", "lens": "reversibility",
        "claim_under_doubt": "doubt-reviewer claim: the generator never overwrites a collision",
        "disproof_attempt": "checked: the header-marker guard is unconditional",
        "file": None, "what_would_resolve_it": "n/a -- disproof failed, claim holds",
    }],
    "summary": "doubt-reviewer: one low doubt, resolved on inspection",
}
_ROLE_PAYLOADS = {"spec": _SPEC_PAYLOAD, "code": _CODE_PAYLOAD, "doubt": _DOUBT_PAYLOAD}


def _stub_resolve(role, worktree_root, model, default):
    return default, "the hardcoded default"


@pytest.fixture
def project(tmp_path):
    return make_project(tmp_path)


def test_three_codex_dispatched_passes_are_genuinely_distinct_in_reviews_json(
    project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `from_doubt_reviewer` (review_findings.py) always joins a doubt's
    # claim/disproof with a real em-dash. `_review_cli_harness.run_tool`
    # launches `record_review_pass.py` inheriting this process's ambient
    # env (no scrubbing, unlike codex_review_transport's own subprocess
    # call) and decodes its stdout as UTF-8 -- on a Windows child process
    # NOT given an explicit UTF-8 IO encoding, stdout defaults to the
    # console codepage (cp1252 on this class of machine), which encodes an
    # em-dash as a single non-UTF-8 byte and breaks that decode the moment
    # `show` echoes this fixture's doubt finding back. Pre-existing
    # environment gotcha, not something prior harness callers hit --
    # none of them call `show` after recording a doubt pass with both
    # `claim_under_doubt` and `disproof_attempt` present.
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")

    init_code, init_output = run_tool(project, "init")
    assert init_code == 0, init_output

    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (True, ""))
    monkeypatch.setattr(transport, "_resolve_codex_binary", lambda: "codex")
    monkeypatch.setattr(transport, "resolve_codex_review_model", _stub_resolve)

    out_dir = project / ".shipwright" / "planning" / "iterate" / RUN_ID
    call_count = {"n": 0}

    for role in ("spec", "code", "doubt"):
        def _run(argv, input, capture_output, encoding, errors, timeout, env, _role=role):  # noqa: A002
            call_count["n"] += 1
            Path(argv[argv.index("-o") + 1]).write_text(
                json.dumps(_ROLE_PAYLOADS[_role]), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        # Scoped to THIS role's call only, via its own `with` block --
        # `transport.subprocess` is the real stdlib module object, shared
        # process-wide with `_review_cli_harness.run_tool`'s own
        # `subprocess.run` call below. An un-scoped `monkeypatch.setattr`
        # here would still be mocking `subprocess.run` when `run_tool`
        # tries to launch the REAL `record_review_pass.py` CLI a few lines
        # down, breaking that unrelated call instead of the intended one.
        with monkeypatch.context() as m:
            m.setattr(transport.subprocess, "run", Mock(side_effect=_run))
            result = transport.run_codex_review(role, project, f"prompt-for-{role}", out_dir)
        assert result["status"] == "completed", result

        record_code, record_output = run_tool(
            project, "record", "--review-type", role, "--status", "completed",
            "--from", f"{role}-reviewer", "--payload-file", result["canonical_path"],
            "--transport", "codex", "--transport-note", result["transport_note"],
        )
        assert record_code == 0, record_output

    # Genuinely distinct DISPATCH: three separate `codex exec` subprocess
    # invocations, one per role -- never one call answering for all three.
    assert call_count["n"] == 3

    show_code, show_output = run_tool(project, "show")
    assert show_code == 0, show_output
    reviews = json.loads(show_output)["reviews"]

    # `transport_note` is deliberately IDENTICAL across all three cascade
    # roles in a run (same static model/effort/sandbox contract for all of
    # them) -- it records the contract, not per-role uniqueness; `review_type`
    # is already what keys a row distinct from its siblings (Internal Plan
    # Review, medium, 2026-09-20). It DOES carry effort and sandbox, closing
    # the parent spec's "evidence records the actual role, model, effort,
    # sandbox... for each required review" bar that a bare model string left
    # unmet.
    expected_note = (
        f"{transport.CODEX_REVIEW_MODEL} effort={transport.CODEX_REVIEW_REASONING_EFFORT} "
        f"sandbox={transport.CODEX_REVIEW_SANDBOX_MODE}"
    )
    for role in ("spec", "code", "doubt"):
        assert reviews[role]["status"] == "completed"
        assert reviews[role]["transport"] == "codex"
        assert reviews[role]["transport_note"] == expected_note

    # Genuinely distinct EVIDENCE: three rows with three different bodies
    # (never the same content recorded three times over). `raw_excerpt`
    # stays `None` for all three by design (native code/spec/doubt-reviewer
    # adapters carry no raw excerpt — only external-review-json/-prose do,
    # review_payloads._findings_from_text); the finding content itself, not
    # that field, is where distinctness has to show up here.
    for role in ("spec", "code", "doubt"):
        assert reviews[role]["raw_excerpt"] is None
    # A whole-row JSON-set-of-3 check was tried here and dropped: each row
    # also carries its own `completed_at` from three sequential `record`
    # calls, so it would pass on timestamp variance alone regardless of
    # payload content -- the per-role finding-text assertions below are what
    # actually prove distinct content (code-reviewer, low, 2026-09-20).

    assert reviews["spec"]["findings_count"] == 1
    assert reviews["code"]["findings_count"] == 1
    assert reviews["doubt"]["findings_count"] == 1

    # A PASS/empty-citations spec payload stores nothing distinctive
    # (`from_spec_reviewer` drops `summary` entirely), so the row-level
    # distinctness check below would pass even if a regression replaced
    # _SPEC_PAYLOAD's content with any other empty-citations PASS -- the
    # payload carries one citation specifically so its own recorded finding
    # text is independently assertable, the same way code/doubt already are
    # (External Review, OpenAI leg, medium, 2026-09-20).
    spec_findings = [f["finding"] for f in reviews["spec"]["findings"]]
    code_findings = [f["finding"] for f in reviews["code"]["findings"]]
    doubt_findings = [f["finding"] for f in reviews["doubt"]["findings"]]
    assert spec_findings and code_findings and doubt_findings
    assert len({tuple(spec_findings), tuple(code_findings), tuple(doubt_findings)}) == 3
    assert any("spec-reviewer citation" in f for f in spec_findings)
    assert any("code-reviewer finding" in f for f in code_findings)
    assert any("doubt-reviewer claim" in f for f in doubt_findings)
