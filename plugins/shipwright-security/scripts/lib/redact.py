#!/usr/bin/env python3
"""Redaction helpers for secret evidence in scanner findings.

Two layers (default-on; opt-out via ``full_evidence=True``):

  1. Allowlist-based structural redaction
     Any field NOT in ``SAFE_FIELD_ALLOWLIST`` is dropped (by deletion, not
     by string substitution — types are preserved). Covers raw-secret fields
     emitted by Gitleaks (``match`` / ``secret`` / ``commit`` / ``author`` /
     ``email`` / ``fingerprint``) plus any future tool-added field.

  2. Free-text content masking on ``description`` / ``remediation_hint``
     Scanner-authored prose may quote the matched secret value verbatim. A
     small set of regex patterns scrubs known-shape and high-entropy strings,
     replacing them with ``REDACTED_TOKEN``.

The two layers are independent — allowlist removes whole-field secrets; the
masker scrubs in-prose secrets in fields that pass the allowlist.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

REDACTED_TOKEN = "<redacted-secret>"

# Fields preserved by the allowlist filter. Add a new field here ONLY after
# confirming it cannot carry raw secret evidence — doing so consciously is
# safer than blocklisting every new tool-added field reactively.
SAFE_FIELD_ALLOWLIST: frozenset[str] = frozenset({
    "id",
    "severity",
    "severity_score",
    "type",
    "rule",
    "cve_id",
    "affected_file",
    "affected_line",
    "affected_package",
    "installed_version",
    "fixed_version",
    "cwe_classes",
    "source",
    "_remediation_class",
    "_remediation_status",
    "description",
    "remediation_hint",
})

# Fields where free-text masking is applied. Both are scanner-authored prose
# that may incidentally embed the matched secret value.
_FREE_TEXT_FIELDS: frozenset[str] = frozenset({"description", "remediation_hint"})


# Known-shape patterns first (anchored by recognisable prefix), then a generic
# high-entropy fallback. Ordering matters — specific patterns mask before the
# entropy fallback can over-match.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Stripe-style live secret keys
    re.compile(r"sk-live-[A-Za-z0-9]{8,}"),
    re.compile(r"sk_live_[A-Za-z0-9]{8,}"),
    re.compile(r"sk_test_[A-Za-z0-9]{8,}"),
    # GitHub PATs / app installation tokens
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    # AWS access key IDs
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ASIA[0-9A-Z]{16}"),
    # Slack tokens
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
    # Bearer-prefixed tokens (JWT or opaque)
    re.compile(r"Bearer\s+[A-Za-z0-9._\-+/=]{16,}"),
    # JWT-shaped triplet (header.payload.signature) — base64url segments
    re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    # Generic high-entropy fallback: continuous run of 32+ base64-ish chars.
    # Letters AND digits required to avoid masking long English words.
    re.compile(r"(?=\w*[A-Za-z])(?=\w*\d)[A-Za-z0-9+/]{32,}={0,2}"),
)


def mask_secrets_in_text(text: str) -> str:
    """Replace known-shape and high-entropy secret values with REDACTED_TOKEN.

    Idempotent: re-masking already-masked text is a no-op (the placeholder
    token doesn't match any pattern).
    """
    if not isinstance(text, str) or not text:
        return text
    masked = text
    for pat in _SECRET_PATTERNS:
        masked = pat.sub(REDACTED_TOKEN, masked)
    return masked


def redact_finding(
    finding: dict[str, Any], *, full_evidence: bool = False,
) -> dict[str, Any]:
    """Return a redacted copy of ``finding``.

    Args:
        finding: a normalized finding dict (typically from backend.scan()).
        full_evidence: if True, return the finding unchanged. Reserved for
            opt-in local-debug contexts; production / CI / shared-disk paths
            should leave this False.

    Returns:
        A new dict; the input is not mutated.
    """
    if full_evidence:
        return dict(finding)

    # Layer 1 — allowlist filter (structural)
    out: dict[str, Any] = {
        k: v for k, v in finding.items() if k in SAFE_FIELD_ALLOWLIST
    }

    # Layer 2 — free-text content masking on whitelisted prose fields
    for field in _FREE_TEXT_FIELDS:
        if field in out and isinstance(out[field], str):
            out[field] = mask_secrets_in_text(out[field])

    return out


def redact_findings(
    findings: Iterable[dict[str, Any]], *, full_evidence: bool = False,
) -> list[dict[str, Any]]:
    """Apply ``redact_finding`` to a list of findings."""
    return [redact_finding(f, full_evidence=full_evidence) for f in findings]
