#!/usr/bin/env python3
"""What each refreshed document SAYS about the state it describes.

Third module of the compliance-evidence refresh
(iterate-2026-07-31-derived-docs-at-release), and its own subject rather than its
own line count: :mod:`tools.compliance_refresh_produce` decides whether there is a
result worth delivering, :mod:`tools.refresh_compliance_docs` decides where it
goes, and this decides what it *claims*.

Two claims, one per producer class:

* **The fixed point** — every markdown document's ``Source-State:`` banner gains
  ``base=<commit>`` and, for a release delivery, ``release=<tag>``. Applied by the
  DELIVERER rather than by the renderer, because only the deliverer knows the
  answer: a renderer running inside an ordinary iterate has no release and no
  base, and inventing one is the failure this whole subject exists to remove.
* **The scan** — ``ci-security.json`` is the one member of the set that does not
  derive from the tree, so its freshness is not a property of the commit it ships
  in. It is reported, never asserted, and never fails the run.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from dataclasses import replace
from pathlib import Path

# UNCONDITIONAL — see the note in `tools/compliance_refresh_produce.py` (ADR-045).
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent  # shared/scripts
sys.path.insert(0, str(_SCRIPTS_DIR))

from lib.churn_merge import CI_SECURITY_SUMMARY  # noqa: E402
from lib.compliance_refresh import CLASSIFICATION  # noqa: E402
from source_state import (  # noqa: E402
    banner_line,
    parse_banner_line,
)

__all__ = ["ci_security_report", "stamp_fixed_point"]

_STAMP_BANNER_RE = re.compile(r"(?m)^Source-State:[^\r\n]*(?P<ending>\r?\n|$)")


def _instant(value: str) -> datetime | None:
    """Parse an ISO-8601 timestamp to a comparable instant, or ``None``.

    NOT a lexical compare. The two sides do not share an offset: ``git show -s
    --format=%cI`` renders in the COMMITTER'S LOCAL offset, while the scanner
    writes ``datetime.now(timezone.utc)``. Comparing the strings therefore reports
    a genuinely older scan as fresh whenever the offsets differ — a false
    "``stale: false``" about a comparison that never happened, which is the same
    collapse the two branches around it refuse (Stage-3 doubt D8).

    A naive timestamp (no offset at all) is refused rather than assumed UTC:
    guessing is what produced the defect.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _git_show_date(root: Path, sha: str) -> str:
    from tools.compliance_refresh_produce import git

    return (git(root, "show", "-s", "--format=%cI", sha).stdout or "").strip()


def stamp_fixed_point(
    payload: dict[str, bytes], base_sha: str, release: str | None,
) -> tuple[dict[str, bytes], list[str]]:
    """Rewrite each document's ``Source-State:`` banner to name the fixed point.

    Applied by the DELIVERER, not by the renderer, because only the deliverer
    knows the answer: a renderer running inside an ordinary iterate has no
    release and no base, and inventing one is the failure mode this whole subject
    exists to remove. It is also why this is not threaded through the generator as
    a flag — that would mean editing ``resolve_churn_conflicts.py``,
    ``cross_component`` machinery, for a value it would only pass along.

    Round-tripped through the banner's own parser and renderer rather than
    patched as a string: values are validated on the way in, an absent or
    unparseable banner is left alone rather than guessed at, and the result is
    exactly one banner line whatever the input. The two ``.json`` members carry no
    banner and are untouched — ``ci-security.json`` states its provenance in its
    own ``source``/``scan_date`` fields, and ``test-traceability.json`` has a
    schema with contract tests that is not this change's to extend.

    Returns ``(payload, stamped_rels)`` — a new dict, and which paths moved.
    """
    stamped: list[str] = []
    out = dict(payload)
    for rel, blob in sorted(payload.items()):
        if not rel.endswith(".md"):
            continue
        try:
            text = blob.decode("utf-8")
        except UnicodeDecodeError:
            continue
        state = parse_banner_line(text)
        if state is None:
            continue
        line = banner_line(replace(state, base=base_sha, release=release))
        # A CALLABLE replacement, never the string. `re.sub` treats a string
        # replacement as a TEMPLATE and expands backslash escapes in it — and
        # `safe_run_id` permits backslashes (it rejects whitespace, braces and
        # control categories, not `\`). So `--release 'v1\x0aSource-State:...'`
        # renders as one physical line, then `re.sub` would expand `\x0a` into a
        # real newline and forge a SECOND banner line in the shipped document —
        # defeating `banner_line`'s "always exactly one line, whatever the input"
        # guarantee from outside it. An accidental escape (`v1\d`, a Windows path
        # fragment) is worse still: `re.error` raised from inside the producer
        # (Stage-2 code review, medium).
        out[rel] = _STAMP_BANNER_RE.sub(
            lambda match: line + match.group("ending"), text, count=1).encode("utf-8")
        stamped.append(rel)
    return out, stamped


def ci_security_report(root: Path, base_sha: str) -> dict:
    """What ``ci-security.json`` actually is, said out loud.

    It is the one path in the set that does NOT derive from the tree: it carries
    whatever the latest COMPLETED ``security.yml`` run reported, which may belong
    to a different commit than the one being shipped. At release time that is fine
    in practice — a scan has just run on the release PR — but assuming all seven
    behave alike is the mistake this exists to prevent (the parked Weg-A iterate's
    H4 finding).

    **Never fails the run**: the operator's decision is explicit that a release is
    not held for a scan that has not landed. What is owed is visibility, and the
    document's own committed ``source``/``scan_date`` fields are the durable form
    of it — tool output is not evidence anybody reads later. ``stale`` adds the one
    relation a reader cannot compute alone: does the scan predate the code it ships
    beside."""
    report: dict = {"classification": CLASSIFICATION[CI_SECURITY_SUMMARY]}
    try:
        summary = json.loads((root / CI_SECURITY_SUMMARY).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        report["stale"] = None  # unknown is not False
        report["note"] = f"unreadable ({type(exc).__name__}) — the committed copy stands"
        return report
    if not isinstance(summary, dict):
        report["stale"] = None
        report["note"] = "not an object — the committed copy stands"
        return report
    report["source"] = summary.get("source") or "(none recorded)"
    report["scan_date"] = summary.get("scan_date") or ""
    base_date = _git_show_date(root, base_sha)
    report["base_date"] = base_date
    scan_at, base_at = _instant(report["scan_date"]), _instant(base_date)
    if scan_at is None or base_at is None:
        # One side missing means the comparison did not happen. Reporting `False`
        # here would answer "is it stale?" with "no" on the strength of never
        # having looked — the same collapse the unreadable branch above refuses.
        report["stale"] = None
        report["note"] = (
            f"scan {report['source']} at {report['scan_date'] or '(undated)'}; "
            "freshness not comparable — a date is missing or unparseable on one side"
        )
    elif scan_at < base_at:
        report["stale"] = True
        report["note"] = (
            f"the committed scan ({report['scan_date']}) predates the base commit "
            f"({base_date}) — it describes older code. Not a blocker."
        )
    else:
        report["stale"] = False
        report["note"] = f"scan {report['source']} at {report['scan_date']}"
    return report
