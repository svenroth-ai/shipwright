"""The Stage-1 adapter — the recording path the gate's own remediation names.

Found by the Stage-3 doubt reviewer, and confirmed by this run having hit it:
the ONE documented way to record the new `spec` row (`--from code-reviewer`)
routes to `from_code_reviewer`, which requires a top-level `review` array.
`plugins/shipwright-build/agents/spec-reviewer.md` pins Stage 1's reply as
`{stage, verdict, spec_citations, summary}` — on PASS *and* REJECT. So handing
the reviewer's reply over verbatim exited 1 `payload_unreadable`, and the
cheapest way past a gate that exists to make Stage 1 provable was to hand-write
a `{"review": [...]}` file — i.e. fabricating the evidence was easier than
recording it.

Every earlier test substituted a code-reviewer payload for Stage 1, which is
exactly why nothing caught it. These drive the REAL shape.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pytest  # noqa: E402

from lib.review_payloads import ADAPTERS, build_findings  # noqa: E402

#: Verbatim from `spec-reviewer.md`'s pinned output contract.
_REJECT = """{
  "stage": "spec-compliance",
  "verdict": "REJECT",
  "spec_citations": [
    {
      "spec_ref": "sections/03-auth.md:L42  (AC-2: 'reject expired tokens')",
      "divergence": "login() never checks token expiry; expired tokens are accepted",
      "diff_location": "src/auth/login.ts:88",
      "kind": "missing"
    }
  ],
  "summary": "1 acceptance criterion not met (AC-2). Code-reviewer not invoked."
}"""

_PASS = """{
  "stage": "spec-compliance",
  "verdict": "PASS",
  "spec_citations": [],
  "summary": "every requirement present, faithful and in scope."
}"""


def test_spec_reviewer_is_a_registered_adapter():
    assert "spec-reviewer" in ADAPTERS


def _write(tmp_path: Path, body: str) -> str:
    path = tmp_path / "reply.json"
    path.write_text(body, encoding="utf-8")
    return str(path)


def test_a_reject_reply_becomes_findings_without_transformation(tmp_path):
    findings, parse_status, raw = build_findings(
        "spec-reviewer", _write(tmp_path, _REJECT))

    assert len(findings) == 1
    finding = findings[0]
    assert finding["source"] == "spec-reviewer"
    # BOTH halves survive: the divergence alone does not say which requirement
    # it breaks, and the citation is the whole point of a Stage-1 finding.
    assert "never checks token expiry" in finding["finding"]
    assert "03-auth.md:L42" in finding["finding"]
    assert finding["file"] == "src/auth/login.ts:88"
    assert finding["category"] == "missing"
    assert parse_status is None and raw is None


def test_a_pass_reply_yields_an_honest_empty_result(tmp_path):
    """`spec_citations: []` is a reviewer saying it found nothing — which is a
    RESULT, not a malformed payload."""
    findings, _, _ = build_findings("spec-reviewer", _write(tmp_path, _PASS))

    assert findings == []


def test_a_missing_citations_array_is_still_malformed(tmp_path):
    """Tolerating the empty array must not tolerate its absence: a reply with no
    `spec_citations` key at all is broken reviewer output, not a clean pass."""
    from lib.review_findings import ReviewFindingsError

    body = '{"stage": "spec-compliance", "verdict": "PASS", "summary": "x"}'
    with pytest.raises(ReviewFindingsError):
        build_findings("spec-reviewer", _write(tmp_path, body))


def test_the_code_reviewer_adapter_still_rejects_a_spec_reply(tmp_path):
    """Pins WHY the adapter was needed. If this ever stops raising, the two
    shapes have converged and the separate adapter can go."""
    from lib.review_findings import ReviewFindingsError

    with pytest.raises(ReviewFindingsError):
        build_findings("code-reviewer", _write(tmp_path, _REJECT))
