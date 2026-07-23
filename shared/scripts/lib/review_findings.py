"""Normalize what each reviewer emits into ONE finding shape.

Four sources, one target (defined in :mod:`lib.review_finding_shape`)::

    {"severity": …, "category": …, "file": …, "line": …,
     "finding": str, "suggestion": …, "source": str}

Three of the four adapters live here and are near-trivial dict mappings, because
the sources are **already structured** — ``code-reviewer`` returns
``{review: [{severity, category, file, line, finding, suggestion}]}`` and
``doubt-reviewer`` returns ``{doubts: [{severity, lens, claim_under_doubt,
disproof_attempt, file, what_would_resolve_it}]}``. The iterate lifecycle simply
never persisted them. Nothing here asks a reviewer to change what it emits; this
stops the emission being thrown away.

The fourth source — external-reviewer prose — needs real parsing and lives in
:mod:`lib.review_prose`; it is re-exported here so callers have one import site.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .review_finding_shape import MAX_FINDINGS, MAX_TEXT_CHARS, coerce_text, make_finding
from .review_prose import (
    PARSE_PARTIAL,
    PARSE_STRUCTURED,
    PARSE_UNSTRUCTURED,
    ProseOverflowError,
    from_external_prose,
)

__all__ = [
    "PARSE_PARTIAL",
    "PARSE_STRUCTURED",
    "PARSE_UNSTRUCTURED",
    "ProseOverflowError",
    "ReviewFindingsError",
    "extract_json_payload",
    "from_code_reviewer",
    "from_doubt_reviewer",
    "from_external_prose",
    "from_self_review",
]


class ReviewFindingsError(ValueError):
    """Raised when a payload cannot be interpreted as a reviewer's output."""


def _items(payload: Any, key: str) -> list[Any]:
    """The result array, which must be PRESENT and a list.

    A missing key is malformed reviewer output, not a clean review: treating
    ``{}`` or ``{"section": "x"}`` as "zero findings" would close a review row
    as clean on the strength of a truncated or wrong-shaped reply. Only an
    explicit ``[]`` means "I looked and found nothing".
    """
    if not isinstance(payload, dict):
        raise ReviewFindingsError(
            f"expected a JSON object with a {key!r} array, got {type(payload).__name__}"
        )
    if key not in payload:
        raise ReviewFindingsError(
            f"payload has no {key!r} key — a missing result array is malformed "
            "reviewer output, not a clean review (an empty array is how a "
            "reviewer says it found nothing)"
        )
    items = payload[key]
    if not isinstance(items, list):
        raise ReviewFindingsError(f"{key!r} is not an array")
    if len(items) > MAX_FINDINGS:
        raise ReviewFindingsError(
            f"{key!r} holds {len(items)} findings, above the {MAX_FINDINGS} cap — "
            "refusing to record a truncated review as complete"
        )
    return items


# --- native adapters --------------------------------------------------------


def _no_element_loss(items: list[Any], out: list[dict[str, Any]], key: str) -> None:
    """A non-empty result array must not evaporate into fewer findings.

    ``_items`` already refuses a MISSING array on the grounds that it is
    malformed output rather than a clean review — but the elements inside a
    present array could still be dropped one by one and land in the identical
    state. The producers are LLMs and a field-name slip (``issue`` where the
    contract says ``finding``) is the likeliest malformation there is, so
    ``{"review": [{"severity": "high", "issue": "..."}]}`` used to record as
    "ran, found nothing" — byte-identical to an honest clean review.
    """
    if len(out) < len(items):
        raise ReviewFindingsError(
            f"{len(items) - len(out)} of {len(items)} {key!r} item(s) carried no "
            "usable finding text — that is malformed reviewer output, not a "
            "clean review; fix the payload rather than recording a silent loss"
        )


def from_code_reviewer(payload: Any) -> list[dict[str, Any]]:
    """``{section, review: [...]}`` — the ``shipwright-build`` code-reviewer."""
    items = _items(payload, "review")
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = coerce_text(item.get("finding"))
        if not text:
            continue
        out.append(make_finding(
            finding=text,
            source="code-reviewer",
            severity=item.get("severity"),
            category=item.get("category"),
            file=item.get("file"),
            line=item.get("line"),
            suggestion=item.get("suggestion"),
        ))
    _no_element_loss(items, out, "review")
    return out


def from_doubt_reviewer(payload: Any) -> list[dict[str, Any]]:
    """``{stage, doubts: [...]}`` — the fresh-context disprove pass.

    A doubt is "claim X, and here is my attempt to disprove it", so the finding
    text keeps BOTH halves: the claim alone is not actionable, and the disproof
    alone loses what it was aimed at.
    """
    items = _items(payload, "doubts")
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        claim = coerce_text(item.get("claim_under_doubt"))
        disproof = coerce_text(item.get("disproof_attempt"))
        if claim and disproof:
            text = f"Claim under doubt: {claim} — {disproof}"
        else:
            text = disproof or claim or ""
        if not text:
            continue
        out.append(make_finding(
            finding=text[:MAX_TEXT_CHARS],
            source="doubt-reviewer",
            severity=item.get("severity"),
            category=item.get("lens"),
            file=item.get("file"),
            line=item.get("line"),
            suggestion=item.get("what_would_resolve_it"),
        ))
    _no_element_loss(items, out, "doubts")
    return out


def from_self_review(payload: Any) -> list[dict[str, Any]]:
    """``{items: [{name, verdict, note}]}`` — the mandatory Self-Review checklist.

    Only ``fail`` verdicts become findings; ``pass`` and ``n/a`` are the absence
    of one. Severity stays ``None``: the checklist reports pass/fail and has no
    severity to report, so assigning one would invent review data.
    """
    items = _items(payload, "items")
    failures = [
        i for i in items
        if isinstance(i, dict)
        and (coerce_text(i.get("verdict"), 32) or "").lower() == "fail"
    ]
    out: list[dict[str, Any]] = []
    for item in failures:
        name = coerce_text(item.get("name"), 120)
        note = coerce_text(item.get("note"))
        text = note or (f"{name} failed self-review" if name else "")
        if not text:
            continue
        out.append(make_finding(finding=text, source="self-review", category=name))
    _no_element_loss(failures, out, "items")
    return out


# --- payload hand-over ------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)
_LABELLED_FENCE_RE = re.compile(r"```json[ \t]*\r?\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json_payload(text: str) -> Any:
    """Read a reviewer payload that may arrive as raw JSON **or** as an agent
    reply with the JSON in a fenced block.

    The orchestrator receives a subagent's answer as a message, not a file.
    Requiring it to hand-extract the JSON first would put a transcription step
    between the reviewer and the record — the step most likely to be skipped,
    and the one whose failure is silent.
    """
    if not isinstance(text, str) or not text.strip():
        raise ReviewFindingsError("payload is empty")

    for pattern in (_LABELLED_FENCE_RE, _FENCE_RE):
        for match in pattern.finditer(text):
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReviewFindingsError(
            "no JSON payload found — expected raw JSON or a ```json fenced block"
        ) from exc
