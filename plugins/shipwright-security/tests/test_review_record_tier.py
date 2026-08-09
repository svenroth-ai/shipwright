"""Behavioral coverage for the trusted PR-review waiver decision."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "plugins" / "shipwright-security" / "scripts" / "tools" / "review_record_tier.py"
spec = importlib.util.spec_from_file_location("review_record_tier", SCRIPT)
tier = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(tier)
from _shipwright_shared_review_lib.review_record_core import make_entry, new_record, upsert_review  # noqa: E402

RUN = "iterate-2026-08-09-review-evidence-tier"
PATH = f".shipwright/planning/iterate/{RUN}/reviews.json"


def completed_record():
    record = new_record(RUN)
    for review_type in ("self", "spec", "code", "doubt", "plan", "external_code", "plan_internal"):
        record = upsert_review(record, make_entry(
            review_type, "completed", recorded_by="reviewer",
        ))
    return record


def test_trusted_waiver_requires_a_valid_completed_record():
    needs_review, reason = tier.decide([PATH], ["skip-pr-review"], completed_record(), trusted_head_approval=True)
    assert needs_review is False
    assert "corroborated" in reason


def test_pr_493_style_not_run_record_requires_review():
    record = completed_record()
    record["reviews"]["code"] = make_entry(
        "code", "not_run", disposition="reviewer was unavailable for this run",
    )
    needs_review, reason = tier.decide([PATH], ["skip-pr-review"], record, trusted_head_approval=True)
    assert needs_review is True
    assert "lacks completed" in reason


def test_legacy_spec_entry_is_read_without_crashing():
    record = completed_record()
    record["reviews"].pop("spec")
    record["gates"] = {"spec": make_entry("spec", "completed", recorded_by="reviewer")}
    needs_review, reason = tier.decide([PATH], ["skip-pr-review"], record, trusted_head_approval=True)
    assert needs_review is False
    assert "corroborated" in reason


def test_forged_minimal_or_wrong_run_record_requires_review():
    minimal = {"reviews": {name: {"status": "completed"} for name in ("self", "spec", "code", "doubt")}}
    needs_review, reason = tier.decide([PATH], ["skip-pr-review"], minimal, trusted_head_approval=True)
    assert needs_review is True
    assert "invalid" in reason

    wrong_run = completed_record()
    wrong_run["run_id"] = "iterate-other"
    needs_review, reason = tier.decide([PATH], ["skip-pr-review"], wrong_run, trusted_head_approval=True)
    assert needs_review is True
    assert "invalid" in reason


def test_evidence_cannot_waive_without_a_trusted_label_or_on_sensitive_paths():
    record = completed_record()
    assert tier.decide([PATH], [], record)[0] is True
    assert tier.decide([PATH, ".github/workflows/ci.yml"], ["skip-pr-review"], record, True)[0] is True
    assert tier.decide([PATH], ["skip-pr-review"], None, True)[0] is True
    assert tier.decide([PATH, PATH.replace(RUN, "iterate-other")], ["skip-pr-review"], record, True)[0] is True
    assert tier.decide([PATH, "shared/scripts/lib/review_record_schema.py"], ["skip-pr-review"], record, True)[0] is True
    assert tier.decide([PATH, "shared/scripts/lib/review_record_core.py"], ["skip-pr-review"], record, True)[0] is True
    assert tier.decide([PATH, "shared/scripts/lib/review_record_legacy.py"], ["skip-pr-review"], record, True)[0] is True
    assert tier.decide([PATH, "plugins/shipwright-security/scripts/tools/review_record_tier.py"], ["skip-pr-review"], record, True)[0] is True
    assert tier.decide([PATH, "shared/scripts/lib/__init__.py"], ["skip-pr-review"], record, True)[0] is True
    assert tier.decide([PATH, "shared/scripts/lib/atomic_write.py"], ["skip-pr-review"], record, True)[0] is True


def test_a_persistent_label_cannot_waive_a_new_unapproved_head():
    needs_review, reason = tier.decide([PATH], ["skip-pr-review"], completed_record())
    assert needs_review is True
    assert "approval" in reason
