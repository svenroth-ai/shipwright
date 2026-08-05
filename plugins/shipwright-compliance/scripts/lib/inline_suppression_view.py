"""Inline-suppression rows for the compliance dashboard — pure + offline.

Inline ``# nosemgrep`` suppressions are the one silencing channel the
accepted-risk register deliberately does NOT cover (see ``accepted_risks``, and
``iterate-2026-08-05-inline-suppression-ratchet`` for the decision). That makes
them the channel most likely to be invisible, which is exactly why the
dashboard states them.

**This section reports visibility, not reconciliation, and says so.** A reader
who sees a count here must not conclude that each site has been reviewed and
dated the way a register entry has — it has not. What the count buys is that
the number cannot grow without a recorded decision, because the anti-ratchet
baseline blocks it.

A separate module rather than a function in ``accepted_risk_view`` only because
that file sits at 294 of its 300 permitted lines; the seam is otherwise
arbitrary and the two are read together.
"""

from __future__ import annotations

import sys
from pathlib import Path

#: ``shared/scripts`` relative to this file: plugins/<p>/scripts/lib/<this>.
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"


def _load_shared():
    """The shared ratchet reader, or ``None`` when it cannot be reached.

    Lazily bootstrapped for the same ADR-045 reason as
    ``accepted_risk_view._load_shared``: this module is reached through
    cross-plugin import chains and must not hard-depend on ``shared/scripts``
    at module level. APPEND to ``sys.path``, never ``insert(0)`` — that
    directory also holds ``lib/`` and ``tools/``, which would shadow a plugin's
    own same-named packages.
    """
    try:
        if str(_SHARED_SCRIPTS) not in sys.path:
            sys.path.append(str(_SHARED_SCRIPTS))
        import inline_suppressions  # noqa: PLC0415

        return inline_suppressions
    except ImportError:
        return None


def inline_suppression_lines(project_root: Path | str) -> list[str]:
    """Markdown lines for the inline-suppression block (``[]`` if nothing).

    Three states are kept distinct, because collapsing them is how an
    unreadable file reads as a clean one (external review, GPT #6):

    * reader unavailable / baseline invalid → a conspicuous warning, no count;
    * zero suppressions → an explicit "none", not an empty section;
    * suppressions present → the per-rule table.
    """
    shared = _load_shared()
    if shared is None:
        return [
            "> ⚠️ Inline suppressions: the shared reader could not be loaded, "
            "so `# nosemgrep` sites are **not** counted here.",
            "",
        ]

    try:
        result = shared.reconcile(project_root)
    except shared.BaselineError as exc:
        return [
            f"> ⚠️ Inline suppressions: `{shared.BASELINE_NAME}` is INVALID and "
            f"was not read — {exc}",
            "",
        ]

    sites, entries = result["sites"], result["entries"]
    total = sum(len(v) for v in sites.values())

    lines = ["**Inline suppressions** (`# nosemgrep`, anti-ratchet baseline):", ""]
    if not total:
        lines += ["No inline suppressions in tracked source.", ""]
    else:
        lines += [
            "| Rule | Sites | Baseline | Recorded under |",
            "|------|-------|----------|----------------|",
        ]
        for rule in sorted(sites):
            entry = entries.get(rule)
            measured = len(sites[rule])
            if entry is None:
                # Suppressed but unrecorded is DRIFT, not an accepted risk.
                # Rendering it as governed would launder it into one.
                allowed, ref = "❌ none", "—"
            else:
                allowed = str(entry["max_sites"])
                if measured > entry["max_sites"]:
                    allowed = f"❌ {allowed} (exceeded)"
                ref = entry["rationale_ref"]
            lines.append(f"| `{rule}` | {measured} | {allowed} | {ref} |")
        lines.append("")

    if result["mode"] != "git":
        lines += [
            "> ⚠️ Not a git tree — the file set came from a filesystem walk, "
            "which is broader and less precise than `git ls-files`.",
            "",
        ]
    if result["unreadable"]:
        lines += [
            "> ⚠️ "
            f"{len(result['unreadable'])} file(s) could not be read, so this "
            "count is **partial**: "
            + ", ".join(f"`{p}`" for p in result["unreadable"]),
            "",
        ]

    # No Shipwright-internal run id here: this block renders into ADOPTER
    # projects, where an `iterate-…` slug resolves to nothing. The reasoning
    # belongs in the artifact; the citation belongs in the framework's own
    # source (`shared/scripts/inline_suppressions.py`). Stage-2 code review.
    lines += [
        "_Inline suppressions are deliberately **not** tracked in the "
        "accepted-risk register: an offline reconciler would have to mirror "
        "the scanner's own suppression semantics and would drift, and a "
        "re-review date does not fit a permanent false positive at a fixed "
        "source site. The control is the anti-ratchet above — the count "
        "cannot grow without a recorded decision. This is visibility, "
        "**not** per-site review: unlike a register entry, no site here "
        "carries an owner or a re-review date._",
        "",
    ]
    return lines
