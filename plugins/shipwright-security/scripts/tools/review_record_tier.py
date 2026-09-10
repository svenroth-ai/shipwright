#!/usr/bin/env python3
"""Decide whether a PR-review waiver has trusted review-record support."""

from __future__ import annotations

import importlib.util
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SHARED_LIB = ROOT / "shared" / "scripts" / "lib"
PACKAGE_NAME = "_shipwright_shared_review_lib"
package_spec = importlib.util.spec_from_file_location(
    PACKAGE_NAME, SHARED_LIB / "__init__.py", submodule_search_locations=[str(SHARED_LIB)],
)
if package_spec is None or package_spec.loader is None:  # pragma: no cover - fixed local package
    raise RuntimeError("shared review-record library is unavailable")
package = importlib.util.module_from_spec(package_spec)
sys.modules[PACKAGE_NAME] = package
package_spec.loader.exec_module(package)

from _shipwright_shared_review_lib.review_record_core import entry_for  # noqa: E402
from _shipwright_shared_review_lib.review_record_schema import validate_record  # noqa: E402

PLUGIN_LIB = Path(__file__).resolve().parent.parent / "lib"
if str(PLUGIN_LIB) not in sys.path:
    sys.path.insert(0, str(PLUGIN_LIB))
from pr_review_generated import is_safe_to_skip_review  # noqa: E402

INTERNAL_REVIEW_TYPES = ("self", "spec", "code", "doubt")
REVIEW_RECORD_RE = re.compile(r"^\.shipwright/planning/iterate/([A-Za-z0-9._-]+)/reviews\.json$")
SENSITIVE_PATH_RE = re.compile(
    r"^(?:"
    r"plugins/.+/(?:hooks|skills|agents)/"
    r"|plugins/shipwright-security/scripts/tools/review_record_tier\.py"
    r"|shared/scripts/lib/"
    # Load-bearing for the required PR-review gate since
    # iterate-2026-08-31-pr-review-deepseek-model: pr_review.py fails the gate
    # closed if this file's `deepseek_routing` block drifts from the exact
    # provider allowlist the code expects — same trust class as the lib code
    # it configures, so a config-only edit here must be reviewed too.
    r"|shared/config/external_review\.json"
    # The keystone AC gate (`.github/workflows/` step below) is "exactly as strong
    # as ci.yml itself" by design (`.shipwright/planning/iterate/2026-09-09-p3-6-
    # keystone-gate.md` §4/§7) — but its own verifier logic lives in separate
    # source modules that weren't named here, so an edit to the logic alone (not
    # the ci.yml step invoking it) escaped the scrutiny an edit to ci.yml gets.
    # Closes triage trg-9967000f. Named by FILE, so a shared helper these modules
    # import (e.g. under `verifiers/_layer_coverage_*`) that also carries
    # keystone-specific logic is NOT covered — those helpers also back an
    # unrelated non-keystone gate, so widening this match to their directory
    # would force mandatory review onto that gate's unrelated maintenance PRs
    # too. Known, deliberately deferred residual gap: trg-a719e3b7.
    r"|shared/scripts/tools/check_keystone_ac_gate\.py"
    r"|shared/scripts/tools/verifiers/_keystone_"
    r"|\.github/workflows/"
    r"|\.github/actions/"
    r"|shared/templates/github-actions/"
    r"|\.trivyignore(?:\.ya?ml)?$"
    r"|shipwright_accepted_risks\.yaml"
    r"|\.semgrepignore"
    r"|\.claude/settings\.json"
    r"|shipwright_bloat_baseline\.json"
    r"|scripts/hooks/"
    r"|scripts/install-hooks\."
    r")"
)


def decide(changed_paths: list[str], labels: list[str], review_record: object | None, trusted_head_approval: bool = False) -> tuple[bool, str]:
    """Return ``(needs_review, reason)`` using only trusted waiver + evidence."""
    if "needs-review" in labels:
        return True, "needs-review label set"
    if "sensitive_path_list_truncated" in changed_paths:
        return True, "changed-file list truncated"
    if any(SENSITIVE_PATH_RE.match(path) for path in changed_paths):
        return True, "sensitive path touched"
    if "skip-pr-review" not in labels:
        return True, "no trusted review waiver"
    matches = [match for path in changed_paths if (match := REVIEW_RECORD_RE.fullmatch(path))]
    if len(matches) != 1:
        return True, "review evidence missing or ambiguous"
    if not trusted_head_approval:
        return True, "no trusted approval for this PR head"
    if review_record is None:
        return True, "review evidence unavailable"
    valid, error = validate_record(review_record, expected_run_id=matches[0].group(1))
    if not valid:
        return True, f"review evidence invalid: {error}"
    if all(entry_for(review_record, review_type).get("status") == "completed" for review_type in INTERNAL_REVIEW_TYPES):
        return False, "trusted waiver corroborated by completed internal reviews"
    return True, "review evidence lacks completed internal passes"


def classify_generated_only(changed_paths: list[str]) -> tuple[bool, str]:
    """Whether stage 2 should post `success` without running a review at all.

    True only when every changed path is BOTH `pr_review_generated
    .is_safe_to_skip_review` AND not a sensitive path (`SENSITIVE_PATH_RE`) —
    the composition, not either check alone, is what "nothing to review"
    means. An empty list, or one carrying the API-cap marker, is never
    classified true: there is nothing positively identified as
    generated-only, and a truncated list cannot be proven complete.

    Deliberately uses `is_safe_to_skip_review`, NOT the broader
    `is_generated_path` (which also hides sections from a model that still
    reviews the rest of the diff — lower stakes than skipping the gate
    entirely; see that function's docstring, added after a Stage-3 doubt
    review caught the broader classifier here).

    Derived from the same trusted, API-read `changed_paths` the tier decision
    above uses — never from stage 1's artifact (FR-01.17 (E)7).
    """
    paths = [p for p in changed_paths if p]
    if not paths or "sensitive_path_list_truncated" in paths:
        return False, ""
    if any(SENSITIVE_PATH_RE.match(p) for p in paths):
        return False, ""
    if not all(is_safe_to_skip_review(p) for p in paths):
        return False, ""
    return True, f"no reviewable content - all {len(paths)} paths are generated artifacts"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changed-paths-file", type=Path, required=True)
    parser.add_argument("--labels-json", required=True)
    parser.add_argument("--review-record-file", type=Path, required=True)
    parser.add_argument("--trusted-head-approval", action="store_true")
    args = parser.parse_args(argv)
    try:
        changed_paths = [line.strip() for line in args.changed_paths_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        labels = json.loads(args.labels_json)
        if not isinstance(labels, list) or not all(isinstance(label, str) for label in labels):
            raise ValueError("labels must be a JSON array of strings")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"needs_review=true\nreason=tier inputs unreadable: {exc}\nall_generated=false\nall_generated_reason=")
        return 0
    review_record: object | None = None
    if args.review_record_file.is_file():
        try:
            review_record = json.loads(args.review_record_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            review_record = None
    needs_review, reason = decide(changed_paths, labels, review_record, args.trusted_head_approval)
    all_generated, all_generated_reason = classify_generated_only(changed_paths)
    print(
        f"needs_review={str(needs_review).lower()}\nreason={reason}\n"
        f"all_generated={str(all_generated).lower()}\nall_generated_reason={all_generated_reason}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
