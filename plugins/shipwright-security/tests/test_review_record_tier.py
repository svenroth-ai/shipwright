"""Behavioral coverage for the trusted PR-review waiver decision."""

import importlib.util
import json
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


def test_waiver_cannot_cover_a_change_to_a_suppression_or_hook_channel():
    """A waiver cannot change what CI is allowed to ignore or how hooks run."""
    record = completed_record()
    sensitive = (
        ".trivyignore",
        ".trivyignore.yml",
        ".trivyignore.yaml",
        "shipwright_accepted_risks.yaml",
        ".semgrepignore",
        ".claude/settings.json",
        "shipwright_bloat_baseline.json",
        "scripts/hooks/pre-commit",
        "scripts/install-hooks.sh",
        "scripts/install-hooks.ps1",
    )
    for path in sensitive:
        assert tier.decide([PATH, path], ["skip-pr-review"], record, True)[0] is True, path


def test_waiver_fails_closed_when_github_truncates_the_changed_path_list():
    record = completed_record()
    needs_review, reason = tier.decide(
        [PATH, "sensitive_path_list_truncated"],
        ["skip-pr-review"],
        record,
        True,
    )
    assert needs_review is True
    assert reason == "changed-file list truncated"


def test_helper_path_is_anchored_against_a_prefixed_bypass():
    assert tier.SENSITIVE_PATH_RE.match("safe/plugins/shipwright-security/scripts/tools/review_record_tier.py") is None
    assert tier.SENSITIVE_PATH_RE.match("plugins/shipwright-security/scripts/tools/review_record_tier.py")


def test_a_persistent_label_cannot_waive_a_new_unapproved_head():
    needs_review, reason = tier.decide([PATH], ["skip-pr-review"], completed_record())
    assert needs_review is True
    assert "approval" in reason


def test_needs_review_label_forces_review_even_with_a_waiver():
    needs_review, reason = tier.decide(
        [PATH], ["needs-review", "skip-pr-review"], completed_record(), trusted_head_approval=True,
    )
    assert needs_review is True
    assert reason == "needs-review label set"


def test_cli_reports_no_waiver_when_labels_are_empty(tmp_path, capsys):
    changed = tmp_path / "changed.txt"
    changed.write_text(f"{PATH}\n", encoding="utf-8")
    exit_code = tier.main([
        "--changed-paths-file", str(changed),
        "--labels-json", "[]",
        "--review-record-file", str(tmp_path / "reviews.json"),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "needs_review=true" in out
    assert "no trusted review waiver" in out


def test_cli_full_waiver_flow_reports_no_review_needed(tmp_path, capsys):
    changed = tmp_path / "changed.txt"
    changed.write_text(f"{PATH}\n", encoding="utf-8")
    record_file = tmp_path / "reviews.json"
    record_file.write_text(json.dumps(completed_record()), encoding="utf-8")
    exit_code = tier.main([
        "--changed-paths-file", str(changed),
        "--labels-json", json.dumps(["skip-pr-review"]),
        "--review-record-file", str(record_file),
        "--trusted-head-approval",
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "needs_review=false" in out
    assert "corroborated" in out


def test_cli_reports_unreadable_inputs_when_labels_json_is_malformed(tmp_path, capsys):
    changed = tmp_path / "changed.txt"
    changed.write_text(f"{PATH}\n", encoding="utf-8")
    exit_code = tier.main([
        "--changed-paths-file", str(changed),
        "--labels-json", "not-json",
        "--review-record-file", str(tmp_path / "reviews.json"),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "needs_review=true" in out
    assert "tier inputs unreadable" in out


def test_cli_reports_unreadable_inputs_when_labels_is_not_a_string_array(tmp_path, capsys):
    changed = tmp_path / "changed.txt"
    changed.write_text(f"{PATH}\n", encoding="utf-8")
    exit_code = tier.main([
        "--changed-paths-file", str(changed),
        "--labels-json", json.dumps({"not": "a list"}),
        "--review-record-file", str(tmp_path / "reviews.json"),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "tier inputs unreadable" in out


def test_cli_reports_unreadable_inputs_when_changed_paths_file_is_missing(tmp_path, capsys):
    exit_code = tier.main([
        "--changed-paths-file", str(tmp_path / "does-not-exist.txt"),
        "--labels-json", "[]",
        "--review-record-file", str(tmp_path / "reviews.json"),
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "tier inputs unreadable" in out


def test_cli_treats_a_malformed_review_record_file_as_missing(tmp_path, capsys):
    changed = tmp_path / "changed.txt"
    changed.write_text(f"{PATH}\n", encoding="utf-8")
    record_file = tmp_path / "reviews.json"
    record_file.write_text("{not valid json", encoding="utf-8")
    exit_code = tier.main([
        "--changed-paths-file", str(changed),
        "--labels-json", json.dumps(["skip-pr-review"]),
        "--review-record-file", str(record_file),
        "--trusted-head-approval",
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "needs_review=true" in out
    assert "review evidence unavailable" in out
