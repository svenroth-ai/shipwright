"""Opt-in strictness for the external-review envelope (issue #1035).

#670 decided that one answering reviewer is enough to proceed, and that stays the default. A
caller that wants *every configured reviewer* to answer asks for it here -- through
``external_review.require_all_legs``, ``--require-all-legs`` or ``--min-reviews N`` -- and gets a
nonzero exit with ``success: false`` and the missing legs named, instead of having to parse stderr.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_STRICT_BANNER = (
    "error: external review INCOMPLETE - {reason}. Strict review was requested "
    "(require_all_legs / --min-reviews), so this pass is NOT a success."
)


def _positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise ValueError(text)
    return value


def add_strict_arguments(parser: Any) -> None:
    """The two CLI spellings of the same opt-in (kept here so the CLI file does not grow)."""
    parser.add_argument(
        "--require-all-legs", action="store_true",
        help="Exit nonzero with success:false unless EVERY configured reviewer answered "
             "(same as external_review.require_all_legs in the project config).",
    )
    parser.add_argument(
        "--min-reviews", type=_positive_int, default=None, metavar="N",
        help="Exit nonzero with success:false unless at least N reviewers answered "
             "(N >= 1; an N above the number of configured reviewers can never be met).",
    )


def strict_config_flag(config: dict[str, Any]) -> bool:
    """``external_review.require_all_legs`` - only a real ``true`` counts; a malformed value
    degrades to the default rather than crashing the review."""
    section = config.get("external_review")
    return isinstance(section, dict) and section.get("require_all_legs") is True


def required_reviews(
    config: dict[str, Any], expected: int, *, require_all: bool = False, min_reviews: int | None = None,
) -> int | None:
    """Minimum successful reviews the caller demands, or ``None`` when no strictness was asked."""
    floors = []
    if require_all or strict_config_flag(config):
        floors.append(expected)
    if min_reviews is not None:
        floors.append(min_reviews)
    return max(floors) if floors else None


def partial_legs_from_payload(review_from: str | None, payload_file: str | None) -> list[str] | None:
    """The missing legs of a one-reviewer pass, read from the recorded envelope; ``None`` otherwise.

    ``record_review_pass.py`` calls this so the review-state marker says ``partial`` without any
    caller having to remember a flag. An unreadable or foreign payload is simply "not partial"."""
    if review_from != "external-review-json" or not payload_file:
        return None
    try:
        data = json.loads(Path(payload_file).read_text(encoding="utf-8"))
        succeeded, expected = data.get("reviews_succeeded"), data.get("reviews_expected")
        short = isinstance(succeeded, int) and isinstance(expected, int) and succeeded < expected
        if not (data.get("partially_degraded") or short):
            return None
        legs = data.get("missing_legs") or data.get("partially_degraded_legs") or []
        return sorted(str(leg) for leg in legs) if isinstance(legs, list) else []
    except (OSError, ValueError, AttributeError, TypeError):
        return None


def missing_legs(reviews: dict) -> list[str]:
    """Every configured leg without a successful reply (failed OR skipped), sorted."""
    return sorted(name for name, r in reviews.items() if r.get("status") != "success")


def apply_strict(output: dict, reviews: dict, min_required: int | None, exit_code: int) -> tuple[dict, int]:
    """Attach ``missing_legs`` and, when ``min_required`` is not met, turn the pass into a failure."""
    missing = missing_legs(reviews)
    output["missing_legs"] = missing
    succeeded = output["reviews_succeeded"]
    if min_required is None or succeeded >= min_required:
        return output, exit_code
    reason = f"{succeeded}/{min_required} required reviews succeeded"
    if missing:
        reason += f"; missing: {', '.join(missing)}"
    output.update({"success": False, "strict_failure": True, "strict_reason": reason})
    print(_STRICT_BANNER.format(reason=reason), file=sys.stderr)
    return output, 1
