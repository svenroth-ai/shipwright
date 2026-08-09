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

INTERNAL_REVIEW_TYPES = ("self", "spec", "code", "doubt")
REVIEW_RECORD_RE = re.compile(r"^\.shipwright/planning/iterate/([A-Za-z0-9._-]+)/reviews\.json$")
SENSITIVE_PATH_RE = re.compile(
    r"^(?:"
    r"plugins/.+/(?:hooks|skills|agents)/"
    r"|plugins/shipwright-security/scripts/tools/review_record_tier\.py"
    r"|shared/scripts/lib/"
    r"|\.github/workflows/"
    r"|\.github/actions/"
    r"|shared/templates/github-actions/"
    r")"
)


def decide(changed_paths: list[str], labels: list[str], review_record: object | None, trusted_head_approval: bool = False) -> tuple[bool, str]:
    """Return ``(needs_review, reason)`` using only trusted waiver + evidence."""
    if "needs-review" in labels:
        return True, "needs-review label set"
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
        print(f"needs_review=true\nreason=tier inputs unreadable: {exc}")
        return 0
    review_record: object | None = None
    if args.review_record_file.is_file():
        try:
            review_record = json.loads(args.review_record_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            review_record = None
    needs_review, reason = decide(changed_paths, labels, review_record, args.trusted_head_approval)
    print(f"needs_review={str(needs_review).lower()}\nreason={reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
