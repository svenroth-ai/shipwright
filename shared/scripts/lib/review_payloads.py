"""Turn a reviewer's reply *file* into normalized findings.

The layer between "an agent said something" and
:mod:`lib.review_findings` / :mod:`lib.review_prose`: it picks the adapter,
reads the file, and returns ``(findings, parse_status, raw_excerpt)``. Split out
of ``tools/record_review_pass.py`` to keep that CLI under the file limit, and
because deciding *how to read a payload* is reusable independently of the
command that stores it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .review_finding_shape import TRUNCATION_MARKER
from .review_findings import (
    PARSE_PARTIAL,
    PARSE_STRUCTURED,
    PARSE_UNSTRUCTURED,
    ReviewFindingsError,
    extract_json_payload,
    from_code_reviewer,
    from_doubt_reviewer,
    from_external_prose,
    from_self_review,
    from_spec_reviewer,
)
from .review_verdict import HISTORICAL_REVIEWER_PAIRS, REVIEWERS, summarize_reviews

__all__ = [
    "ADAPTERS", "MAX_RAW_EXCERPT", "build_findings", "build_review_evidence",
    "build_reviewer_verdicts",
]

ADAPTERS = (
    "code-reviewer",
    "spec-reviewer",
    "doubt-reviewer",
    "self-review",
    "external-review-json",
    "external-prose",
    "none",
)

MAX_RAW_EXCERPT = 4000

_NATIVE = {
    "code-reviewer": from_code_reviewer,
    "spec-reviewer": from_spec_reviewer,
    "doubt-reviewer": from_doubt_reviewer,
    "self-review": from_self_review,
}


def _read(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ReviewFindingsError(f"cannot read --payload-file {path}: {exc}") from exc


def _bounded(text: str, limit: int) -> str:
    """Bound an excerpt, marking it when it was shortened — a raw excerpt that
    stops mid-sentence with no marker reads as the reviewer's actual ending."""
    if len(text) <= limit:
        return text
    return text[: max(0, limit - len(TRUNCATION_MARKER))] + TRUNCATION_MARKER


def _from_external_review_json(text: str) -> tuple[list[dict[str, Any]], str, str | None]:
    """Adapt ``external_review.py`` output — merge every provider leg.

    Each leg is prose, so each is parsed independently and the results are
    concatenated: two reviewers finding the same defect is two findings, which
    is honest. Deduplicating them would need a similarity judgement this layer
    has no business making.

    ``parse_status`` is per-PAYLOAD but derived per-LEG: ``structured`` only
    when every non-empty leg parsed, ``partial`` when some did and some did not,
    ``unstructured`` when none did. Reporting ``structured`` because one leg of
    two parsed would hide the fact that an entire provider's review was lost.
    Each leg also gets its own slice of the raw-excerpt budget, so a verbose
    first leg cannot crowd out the evidence of the leg that failed to parse.
    """
    payload = extract_json_payload(text)
    if not isinstance(payload, dict):
        raise ReviewFindingsError("external review output is not a JSON object")
    reviews = payload.get("reviews")
    if not isinstance(reviews, dict):
        raise ReviewFindingsError("external review output has no 'reviews' object")

    # EVERY provider leg counts toward the denominator, including one that
    # errored and therefore carries no `feedback` at all. Filtering those out
    # first would let one good leg of two report `structured` — hiding the
    # likelier loss mode (a provider that failed) while guarding only the rarer
    # one (a provider that replied unparseably).
    all_legs = [(p, leg) for p, leg in sorted(reviews.items()) if isinstance(leg, dict)]
    if not all_legs:
        return [], PARSE_UNSTRUCTURED, None

    budget = max(200, MAX_RAW_EXCERPT // len(all_legs))
    findings: list[dict[str, Any]] = []
    excerpts: list[str] = []
    parsed_legs = 0
    for provider, leg in all_legs:
        feedback = leg.get("feedback")
        if not isinstance(feedback, str) or not feedback.strip():
            reason = leg.get("reason") or leg.get("status") or "no feedback returned"
            excerpts.append(f"[{provider}] <no review returned: {reason}>")
            continue
        excerpts.append(f"[{provider}] {_bounded(feedback, budget)}")
        leg_findings, parse_status = from_external_prose(feedback)
        if parse_status == PARSE_STRUCTURED:
            parsed_legs += 1
        findings.extend(leg_findings)

    if parsed_legs == len(all_legs):
        status = PARSE_STRUCTURED
    elif parsed_legs:
        status = PARSE_PARTIAL
    else:
        status = PARSE_UNSTRUCTURED
    return findings, status, "\n\n".join(excerpts) or None


def _findings_from_text(
    adapter: str, text: str
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    if adapter == "none":
        return [], None, None
    if adapter == "external-prose":
        findings, parse_status = from_external_prose(text)
        return findings, parse_status, _bounded(text, MAX_RAW_EXCERPT) or None
    if adapter == "external-review-json":
        return _from_external_review_json(text)

    native = _NATIVE.get(adapter)
    if native is None:
        raise ReviewFindingsError(f"unknown adapter: {adapter}")
    return native(extract_json_payload(text)), None, None


def build_findings(
    adapter: str, payload_file: str | None
) -> tuple[list[dict[str, Any]], str | None, str | None]:
    """Return normalized findings from one payload snapshot."""
    return build_review_evidence(adapter, payload_file)[:3]


def _verdicts_from_text(adapter: str, text: str) -> dict[str, str] | None:
    if adapter != "external-review-json":
        return None
    payload = extract_json_payload(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("reviews"), dict):
        raise ReviewFindingsError("external review output has no 'reviews' object")
    review_schema = payload.get("review_schema")
    # Schema 2's envelope SHAPE never bumped across the DeepSeek->GLM reviewer
    # swap, so it covers both the current roster and DeepSeek's now-historical
    # one — a schema-2 payload written before this swap must stay readable.
    expected_candidates = (
        (frozenset(REVIEWERS), frozenset(HISTORICAL_REVIEWER_PAIRS[1]))
        if review_schema == 2
        else (frozenset(HISTORICAL_REVIEWER_PAIRS[0]),)
        if review_schema in (None, 1)
        else None
    )
    if expected_candidates is None:
        raise ReviewFindingsError(f"unsupported external review schema {review_schema!r}")
    verdicts = summarize_reviews(payload["reviews"])["verdicts"]
    if frozenset(verdicts) not in expected_candidates:
        raise ReviewFindingsError(
            f"external review schema {review_schema!r} does not match reviewer roster"
        )
    return verdicts


def build_review_evidence(
    adapter: str, payload_file: str | None
) -> tuple[list[dict[str, Any]], str | None, str | None, dict[str, str] | None]:
    """Derive findings and verdicts from one immutable in-memory snapshot."""
    if adapter == "none":
        return [], None, None, None
    if not payload_file:
        raise ReviewFindingsError(f"--from {adapter} requires --payload-file")
    text = _read(payload_file)
    return (*_findings_from_text(adapter, text), _verdicts_from_text(adapter, text))


def build_reviewer_verdicts(
    adapter: str, payload_file: str | None
) -> dict[str, str] | None:
    """Derive verdicts from the full reviewer legs, never a payload summary."""
    if adapter != "external-review-json":
        return None
    if not payload_file:
        raise ReviewFindingsError("--from external-review-json requires --payload-file")
    return _verdicts_from_text(adapter, _read(payload_file))
