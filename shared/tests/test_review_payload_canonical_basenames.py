"""Unit coverage for `lib.review_payloads.CANONICAL_PAYLOAD_BASENAMES` and its
validator — the producer-side half of closing trg-3b206c08. See
`plugins/shipwright-security/scripts/lib/pr_review_generated.py`'s Round 5 note
for the classifier-side gap this canonicalization unblocks (a separate change).
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SHARED / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.review_payloads import (  # noqa: E402
    CANONICAL_PAYLOAD_BASENAMES,
    canonical_basename_error,
)
from lib.review_record_schema import RECORDABLE_TYPES  # noqa: E402

from _review_cli_harness import RUN_ID, make_project, run_tool  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PATH = (_REPO_ROOT / "plugins" / "shipwright-build" / "scripts" / "hooks"
              / "write-review-payload-on-stop.py")


def _load_hook():
    """Loaded by path, not imported — this hook is deliberately self-contained
    (zero non-stdlib imports, see its own docstring), which is exactly what
    makes an ADR-045-style file-path load safe here despite the two `lib`
    packages (`shared/scripts/lib`, `plugins/shipwright-build/scripts/lib`)
    this test process can never import together."""
    spec = importlib.util.spec_from_file_location("write_review_payload_on_stop", _HOOK_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_every_recordable_type_except_plan_internal_has_a_canonical_basename():
    """`plan_internal` is metadata-only (no payload file); every other
    recordable type must have exactly one canonical name to close."""
    assert set(CANONICAL_PAYLOAD_BASENAMES) == set(RECORDABLE_TYPES) - {"plan_internal"}


def test_the_reply_family_matches_what_the_pr_review_classifier_already_anchors_to():
    """`spec`/`code`/`doubt` MUST stay byte-identical to the exact basenames
    `pr_review_generated._REVIEW_EVIDENCE_RE_RUN_ANCHORED` already expects
    (closed against a full-history survey in iterate-2026-09-11-pr-review-
    evidence-filter-gap) — this dict does not get to invent new ones."""
    assert CANONICAL_PAYLOAD_BASENAMES["spec"] == "spec_review_reply.json"
    assert CANONICAL_PAYLOAD_BASENAMES["code"] == "code_review_reply.json"
    assert CANONICAL_PAYLOAD_BASENAMES["doubt"] == "doubt_review_reply.json"


def test_a_canonical_basename_passes_validation():
    for review_type, basename in CANONICAL_PAYLOAD_BASENAMES.items():
        assert canonical_basename_error(review_type, f"/run-dir/{basename}") is None


def test_a_non_canonical_basename_is_rejected_with_the_expected_name():
    error = canonical_basename_error("code", "/run-dir/code-review.json")
    assert error is not None
    assert "code_review_reply.json" in error
    assert "code-review.json" in error
    assert "trg-3b206c08" in error


def test_a_type_with_no_payload_file_kind_is_never_rejected():
    """`plan_internal` records no payload file; an unexpected one is not this
    validator's problem — the adapter layer handles that."""
    assert canonical_basename_error("plan_internal", "/run-dir/whatever.json") is None


def test_the_salvage_hooks_own_mirror_dict_matches_the_shared_registry():
    """`write-review-payload-on-stop.py` cannot import this module (ADR-044 —
    it has its own `lib` package to keep separate), so it duplicates the three
    names it needs in a local `CANONICAL_BASENAME` dict. Nothing else pins the
    two together; a rename here that forgets that mirror would silently make
    the hook's fallback output unrecordable."""
    hook = _load_hook()
    assert hook.CANONICAL_BASENAME == {
        review_type: CANONICAL_PAYLOAD_BASENAMES[review_type]
        for review_type in hook.CANONICAL_BASENAME
    }


def test_the_hooks_salvaged_output_round_trips_into_record(tmp_path, monkeypatch):
    """End-to-end producer/consumer proof, not just the two dicts above: the
    hook's fallback write must be something `record_review_pass.py record
    --payload-file` actually accepts, since that hand-off is the whole point
    of trg-3b206c08."""
    hook = _load_hook()
    project = make_project(tmp_path)
    run_tool(project, "init")

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text("\n".join(json.dumps(entry) for entry in [
        {"role": "user", "content": f"Review this diff for {RUN_ID}."},
        {"role": "assistant", "content": '{"section": "x", "review": []}'},
    ]), encoding="utf-8")

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"transcript_path": str(transcript)})))
    monkeypatch.setattr("sys.stderr", io.StringIO())
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(project))
    assert hook.main(["--review-type", "code"]) == 0

    salvaged = hook.salvage_path(project, RUN_ID, "code")
    assert salvaged.name == CANONICAL_PAYLOAD_BASENAMES["code"]
    assert salvaged.exists()

    code, output = run_tool(
        project, "record", "--review-type", "code", "--status", "completed",
        "--from", "code-reviewer", "--payload-file", str(salvaged),
    )
    assert code == 0, output


def test_iteration_reviews_doc_restates_every_canonical_basename():
    """The SKILL prose table is what an agent actually reads at runtime —
    more likely to drift than this dict. Its own closing sentence promises to
    always restate `CANONICAL_PAYLOAD_BASENAMES` verbatim; hold it to that."""
    doc = (_REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
           / "references" / "iteration-reviews.md").read_text(encoding="utf-8")
    for basename in CANONICAL_PAYLOAD_BASENAMES.values():
        assert basename in doc, f"{basename!r} missing from iteration-reviews.md"
