"""Reading the pre-S6 source and this run's shipped documents (campaign S7).

Helpers only — assertions live in ``test_fr_history_recovery_provenance.py``
(is the recovery complete?) and ``test_fr_history_published_counts.py`` (do the
shipped documents quote what the tables hold?). Split out so neither test module
crosses the size limit and so both read the documents the same way.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


from _fr_history_recovered_history import PRE_S6_COMMIT

REPO = Path(__file__).resolve().parents[1]

#: ``(path, must_exist)``. The changelog drop is consumed at release
#: (``aggregate_changelog`` unlinks processed drops), so its absence is
#: tolerated — the permanent documents never may be. Same shape as the
#: three-document pin S6 had to repair after it broke on a released drop.
SHIPPED_DOCUMENTS = (
    (".shipwright/planning/adr/110-change-history-as-a-derived-view.md", True),
    (".shipwright/agent_docs/decision_log.md", True),
    (".shipwright/planning/iterate/2026-07-19-traceability-derived-view-miniplan.md", True),
    ("CHANGELOG-unreleased.d/Changed/iterate-2026-07-19-traceability-derived-view_001.md", False),
)

#: Exact strings that were published and retracted. Asserting their ABSENCE is
#: stricter and far less brittle than proving the presence of every correct
#: phrasing: these are the literal bytes that shipped, so any reappearing means
#: the correction was reverted.
RETRACTED_COUNT_CLAIMS = (
    "six are returned verbatim",
    "six returned verbatim",
    "| Returned verbatim | 6 |",
    "**6 returned verbatim**",
    "six pairs are returned verbatim",
)

#: Retracted TECHNICAL claims — same rule, different subject. The count pin
#: covered only numbers, so a retracted statement *about the code* survived a
#: full round untouched: the mini-plan went on saying newlines were "already
#: collapsed by ``split()``" after that had been shown false (``tty_sanitize``
#: preserves ``\n`` and ``\t`` by design, and the collapse covered one rendered
#: field of six). A retraction that only covers numbers is half a retraction.
RETRACTED_TECHNICAL_CLAIMS = (
    "newlines already collapsed by",
    "newlines are already collapsed",
)

#: A retracted string is ALLOWED where the surrounding text marks it as
#: retracted — the ADR, the mini-plan and ``degraded[]`` all quote the wrong
#: claim in order to record that it was wrong. Without this, the fix would
#: forbid documenting the defect it fixes.
_RETRACTION_MARKERS = (
    "retract", "first draft", "published", "self-inflicted",
    "arithmetic", "against a table", "no longer", "was wrong",
)

#: A measurement quoted as a SUPERSEDED value is the subject matter, not a
#: stale claim: this run's own event records ``60 of 341`` and is deliberately
#: left unamended, because the log is append-only and the figure was true when
#: written. Without this allowance, the record explaining the divergence would
#: trip the check on that divergence.
SUPERSEDED_MARKERS = (
    "unamended", "append-only", "both are correct", "before it was appended",
    "superseded", "at the time", "measured mid-build", "shipped as",
)

_RUN_ID_RE = re.compile(r"iterate-[0-9][A-Za-z0-9._-]*")


def pre_s6_sections() -> dict[str, str]:
    """Each requirement's own section of the pre-S6 catalog, keyed by FR id.

    Scoped ``### FR-xx.yy`` to the NEXT ``###`` — not to end of file, which is
    the slice that makes the final requirement appear to carry every remaining
    block in the document.

    **Fails hard when the commit is unreachable; never skips.** Six test nodes
    route through here, including the set-equality completeness check that is
    the entire fix for "was a run id dropped from the recovery?". A
    ``pytest.skip`` would delete that check on any shallow CI clone and report
    green — which is the same silent loss as a deleted test, and precisely the
    class of defect this module exists to detect. The remedy is a configuration
    change (``fetch-depth: 0``), so an actionable red is strictly better than a
    quiet pass.
    """
    proc = subprocess.run(
        ["git", "show", f"{PRE_S6_COMMIT}:.shipwright/planning/01-adopted/spec.md"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8",
    )
    if proc.returncode != 0:
        raise AssertionError(  # never pytest.skip -- see the docstring
            f"cannot read the pre-S6 catalog at {PRE_S6_COMMIT}: {proc.stderr.strip()}\n"
            f"The recovered-history checks compare against that commit, so they "
            f"cannot run without it — and skipping them would report green while "
            f"verifying nothing.\n"
            f"Remedy: give the checkout full history (actions/checkout with "
            f"`fetch-depth: 0`, or `git fetch --unshallow`)."
        )

    lines = proc.stdout.splitlines()
    heads = [i for i, ln in enumerate(lines) if ln.startswith("### ")]
    out: dict[str, str] = {}
    for n, i in enumerate(heads):
        match = re.match(r"### (FR-\d+\.\d+)", lines[i])
        if match:
            end = heads[n + 1] if n + 1 < len(heads) else len(lines)
            out[match.group(1)] = "\n".join(lines[i:end])
    return out


def run_ids_in(text: str) -> set[str]:
    """Distinct run-id tokens appearing anywhere in ``text``."""
    return set(_RUN_ID_RE.findall(text))


def document_text(rel: str) -> str | None:
    """A shipped document's text, scoped to this run where the file is shared.

    ``None`` when the file is absent — the caller decides whether that is
    tolerable for that document.
    """
    path = REPO / rel
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if rel.endswith("decision_log.md"):
        marker = "### ADR-328"
        assert marker in text, "ADR-328 is no longer in the decision log"
        start = text.index(marker)
        nxt = text.find("\n### ", start + 1)
        text = text[start:nxt if nxt != -1 else len(text)]
    return text


def retracted_claims_stated_as_current(text: str) -> list[str]:
    """Occurrences of a retracted claim that are NOT marked as retracted.

    Covers both count claims and technical ones. Restricting this to numbers is
    what let a retracted statement about the code stand as current for a whole
    round while the numeric retraction beside it was policed.
    """
    found: list[str] = []
    lowered = text.lower()
    for bad in RETRACTED_COUNT_CLAIMS + RETRACTED_TECHNICAL_CLAIMS:
        for match in re.finditer(re.escape(bad.lower()), lowered):
            window = lowered[max(0, match.start() - 250):match.end() + 250]
            if not any(marker in window for marker in _RETRACTION_MARKERS):
                found.append(bad)
                break
    return found
