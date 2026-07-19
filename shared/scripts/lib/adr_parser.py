"""ADR body parser for the Phase-Quality Q1 "ADR substance" check.

Complements ``lib.adr_headers.parse_adr_headers`` (which only extracts
id, title, status, supersedes) with a body-section extractor so Q1 can
measure whether the latest ADR has a non-trivial Context, Decision and
Consequences section. Q1 is Tier-2 heuristic — the thresholds are
intentionally forgiving (50/30/30 chars, plan § 7 R13).

Supported shapes — Shipwright's decision_log.md mixes two layouts:

1. **Bullet form (Shipwright iterate ADRs):**

       ### ADR-019: Title
       - **Date:** 2026-04-13
       - **Context:** long context text, possibly several clauses.
       - **Decision:** what we chose.
       - **Consequences:** what follows.

2. **Section form (older project ADRs and .shipwright/agent_docs templates):**

       ### ADR-005: Title
       **Context**
       free text context spanning multiple paragraphs.

       **Decision**
       free text decision.

       **Consequences**
       free text consequences.

Both variants reduce to ``(label, body_text)`` pairs which the Q1 check
then measures by character count. Parsing is best-effort and pure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .adr_headers import ADRHeader, parse_adr_headers


# Matches bullet-form labels like "- **Context:** ..." or
# "- **Context**: ..." (Shipwright convention mixes both — the colon can
# sit inside or outside the bold markers).
_BULLET_LABEL_RE = re.compile(
    r"^-\s*\*\*(?P<label>[A-Za-z][A-Za-z _-]*):?\*\*\s*:?\s*(?P<rest>.*)$",
)

# Matches section-form labels like "**Context**" on a line of its own.
_SECTION_LABEL_RE = re.compile(
    r"^\*\*(?P<label>[A-Za-z][A-Za-z _-]*):?\*\*\s*:?\s*$",
)

# Normalise label name → canonical key.
_LABEL_ALIASES: dict[str, str] = {
    "context": "context",
    "background": "context",
    "problem": "context",
    "decision": "decision",
    "choice": "decision",
    "resolution": "decision",
    "consequences": "consequences",
    "consequence": "consequences",
    "impact": "consequences",
    "implications": "consequences",
    "rationale": "rationale",
    "rejected": "rejected",
    "alternatives": "rejected",
    "status": "status",
    "date": "date",
    "section": "section",
    "commit": "commit",
}


@dataclass(frozen=True)
class ADRBody:
    """Parsed body of one ADR header.

    ``sections`` keys are canonical (see ``_LABEL_ALIASES``); values are
    the raw, whitespace-stripped body text, joined across any continuation
    lines. Missing labels are simply absent from the dict.
    """

    header: ADRHeader
    sections: dict[str, str] = field(default_factory=dict)

    def get(self, key: str) -> str:
        return self.sections.get(key, "")


def _normalise_label(raw: str) -> str | None:
    key = raw.strip().lower().replace("_", " ").replace("-", " ")
    # Collapse inner whitespace so "Consequences " matches.
    key = re.sub(r"\s+", " ", key).strip()
    return _LABEL_ALIASES.get(key)


def _extract_body_lines(content: str, header: ADRHeader, next_header: ADRHeader | None) -> list[str]:
    lines = content.splitlines()
    start = header.line_no  # line numbers are 1-based; skip the header line itself
    end = (next_header.line_no - 1) if next_header else len(lines)
    return lines[start:end]


def _parse_adr_body(body_lines: Iterable[str]) -> dict[str, str]:
    """Walk a single ADR body and group text by canonical label."""
    sections: dict[str, list[str]] = {}
    current: str | None = None

    def _commit_trailing(text: str) -> None:
        if current is None:
            return
        stripped = text.rstrip()
        if not stripped:
            return
        sections.setdefault(current, []).append(stripped)

    for raw in body_lines:
        stripped = raw.strip()
        if not stripped:
            # Blank lines end a section-form paragraph group — but we
            # keep accumulating bullet-form into the same label.
            continue

        bullet = _BULLET_LABEL_RE.match(stripped)
        section = _SECTION_LABEL_RE.match(stripped)

        if bullet:
            label = _normalise_label(bullet.group("label"))
            if label is None:
                # Unknown bullet label: continuation of prior text.
                _commit_trailing(stripped)
                continue
            current = label
            rest = bullet.group("rest").strip()
            if rest:
                sections.setdefault(current, []).append(rest)
            continue

        if section:
            label = _normalise_label(section.group("label"))
            if label is None:
                _commit_trailing(stripped)
                continue
            current = label
            continue

        # Plain body line — continuation of the current label.
        _commit_trailing(stripped)

    return {k: " ".join(v).strip() for k, v in sections.items()}


def parse_adr_bodies(content: str) -> list[ADRBody]:
    """Return every ADR in ``content`` paired with its parsed body sections.

    Preserves the source order from ``parse_adr_headers`` so callers can
    pick "the latest ADR" via ``[-1]`` without re-scanning.
    """
    headers = parse_adr_headers(content)
    bodies: list[ADRBody] = []
    for i, header in enumerate(headers):
        next_header = headers[i + 1] if i + 1 < len(headers) else None
        body_lines = _extract_body_lines(content, header, next_header)
        bodies.append(ADRBody(header=header, sections=_parse_adr_body(body_lines)))
    return bodies


def latest_adr_body(content: str) -> ADRBody | None:
    bodies = parse_adr_bodies(content)
    return bodies[-1] if bodies else None


__all__ = [
    "ADRBody",
    "latest_adr_body",
    "parse_adr_bodies",
]
