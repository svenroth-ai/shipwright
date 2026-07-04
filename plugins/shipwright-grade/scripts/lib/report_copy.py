"""report_copy — plain-language, audience-facing copy for the HTML report.

The scoring engine (`control_grade.py`) emits precise but jargon-y details
("re-verify changed requirements (ISO/IEC/IEEE 12207)"). The public report is a
**marketing instrument for non-experts** — someone with an AI-built repo who is
NOT a compliance engineer. So the HTML renderer overlays this human copy: for
each dimension a plain question, a one-line "what this checks", and an
expandable "why it matters" that leads with a **concrete everyday scenario**,
then what improves once you adopt Shipwright.

**Honesty is load-bearing** (over-claiming gets debunked). Every "With
Shipwright" line claims the *enforced mechanism* — never perfection:
- traceability claims "linked to a requirement **or** explicitly classified",
  not "every change maps to a feature" (much day-to-day work is honest no-FR);
- test-health claims "a real run passes", NOT coverage depth (carries a one-line
  honest limit that points to reconciliation);
- reconciliation "flags every behavior-affecting change until re-proven" (not
  "won't let it through"); size = "no unchecked growth" (not "files stay small").
Each claim is credibility-anchored to a recognized external standard (SLSA,
OWASP, NIST SSDF, ISO 25010, OpenSSF Scorecard, and the change-control discipline
banks/insurers are audited on) — and separately validated by Shipwright dogfooding
its own grade (a live A on all seven dimensions).

Pure trusted data (no repo input), keyed by the engine dimension key.
"""

from __future__ import annotations

# Each entry: q (plain question / subtitle), visible (always-shown one-liner),
# scenario (the concrete story + what it checks), improves (the honest "With
# Shipwright" line), limit (optional honest caveat, ""), backed_by (credibility).
DIMENSION_COPY: dict[str, dict[str, str]] = {
    "requirement_traceability": {
        "q": "Can you explain why every piece of code exists?",
        "visible": "Every change should trace back to a reason you asked for it — "
                   "and your features should be backed by tests.",
        "scenario": "Build fast with AI and code piles up. Six months later you "
                    "find a function and nobody remembers what it's for, or "
                    "whether it's safe to delete — and \"it has tests\" often "
                    "means a few test files nobody runs. This checks whether each "
                    "change is tied to a requirement (or honestly marked as "
                    "maintenance), and whether your features are traced to tests.",
        "improves": "With Shipwright, every change is linked to the requirement "
                    "it serves or explicitly classified as maintenance, and "
                    "features are traced to their tests — so your repo stays "
                    "explainable instead of a pile no one dares touch.",
        "limit": "",
        "backed_by": "The change-control discipline banks and insurers get "
                     "audited on.",
    },
    "test_health": {
        "q": "Do your tests actually run and pass — recently?",
        "visible": "Not \"are there test files\" — did the test suite actually "
                   "run lately, and pass?",
        "scenario": "A repo can be full of tests nobody has run in months, or a "
                    "suite that's half-red that everyone ignores. That's false "
                    "confidence — the worst kind. This checks for a real, recent "
                    "run where (almost) everything passed, reading your CI's "
                    "actual test results where they exist.",
        "improves": "With Shipwright, the suite runs on every change and the "
                    "result is recorded with a date — \"it's green\" becomes a "
                    "fact, not a hope.",
        "limit": "One honest limit: this checks that tests run and pass, not how "
                 "much of your code they cover — and green tests alone don't "
                 "prove the whole app works. That deeper check is what "
                 "Reconciliation adds.",
        "backed_by": "OpenSSF Scorecard's \"automated tests run\" signal — the "
                     "same check used across ~1M repositories.",
    },
    "change_traceability": {
        "q": "Can you see who changed what, and why?",
        "visible": "Every change should leave a paper trail — a commit, and the "
                   "reason it happened.",
        "scenario": "AI can make dozens of edits an afternoon. If your history is "
                    "a wall of \"update\", \"fix\", \"wip\", you can't review it, "
                    "audit it, or safely undo one thing. This checks whether "
                    "changes are tied to a commit and a reason (an issue, a task, "
                    "a requirement).",
        "improves": "With Shipwright, every change is recorded like a logbook "
                    "entry — what changed, why, which requirement, which test — "
                    "so your history reads like a story, not a mystery.",
        "limit": "",
        "backed_by": "Software supply-chain provenance (SLSA).",
    },
    "change_reconciliation": {
        "q": "When an AI change touches a feature, is that feature re-checked?",
        "visible": "The one control almost nobody has: when a change quietly "
                   "affects a feature, its tests run again — so side-effects "
                   "can't slip through unseen.",
        "scenario": "You ask the AI to \"fix the login bug.\" It fixes login — "
                    "but it also quietly changes how passwords get checked. Did "
                    "anyone re-test the password check? Usually nobody noticed "
                    "the side-effect, so nobody re-tested it. That's the bug that "
                    "ships to your users. This is the biggest risk of building "
                    "with AI, and almost no tool catches it — because it needs a "
                    "system that knows which change touched which feature.",
        "improves": "That's exactly what Shipwright adds: it flags every "
                    "behavior-affecting change until that feature is proven to "
                    "still work. This is why we can't see it from the outside — "
                    "and why your grade jumps the moment you adopt.",
        "limit": "",
        "backed_by": "How regulated industries like banks and insurers "
                     "re-verify a requirement whenever a change touches it.",
    },
    "security": {
        "q": "Any known-dangerous holes sitting open?",
        "visible": "Did a security scan run recently — and come back clean of "
                   "serious issues?",
        "scenario": "AI happily copies insecure patterns it learned online — a "
                    "leaked key here, an injectable query there. If nobody scans, "
                    "you're guessing about your risk. This checks for a recent "
                    "scan with no open high-severity issues.",
        "improves": "With Shipwright, security scans run inside your build and "
                    "block a change that introduces something critical — "
                    "\"secure\" is enforced, not hoped for. (N/A here just means "
                    "we couldn't see a scan from the outside — run it with "
                    "network access, or adopt to switch it on.)",
        "limit": "",
        "backed_by": "NIST secure-development guidance / OWASP.",
    },
    "maintainability": {
        "q": "Is the codebase staying sane, or ballooning?",
        "visible": "Are files staying a reasonable size, or is the code quietly "
                   "growing into a mess?",
        "scenario": "AI loves to generate giant files and paste the same logic "
                    "five times. It works today — but every month it gets harder "
                    "to change anything without breaking three other things. This "
                    "checks whether files stay a reasonable size (and, once you "
                    "adopt, whether each change quietly adds bloat).",
        "improves": "With Shipwright, unchecked growth is prevented — code size "
                    "is tracked on every change and net growth gets flagged — so "
                    "the codebase stays workable as it grows.",
        "limit": "",
        "backed_by": "ISO 25010 maintainability.",
    },
    "dependency_hygiene": {
        "q": "Do you actually know what's inside your dependencies?",
        "visible": "Do you know every package you depend on — and whether its "
                   "license is safe to ship?",
        "scenario": "AI adds packages without a second thought. Some carry "
                    "licenses that legally force you to open-source your code; "
                    "some are abandoned or risky. Most teams have no idea what's "
                    "actually in there. This checks whether your dependencies are "
                    "inventoried and their licenses resolved — no nasty surprises.",
        "improves": "With Shipwright, you get a full list of everything you "
                    "depend on plus a flag on any license or risk surprise — "
                    "automatically.",
        "limit": "",
        "backed_by": "OWASP \"Vulnerable & Outdated Components.\"",
    },
}

# Shown in place of the engine detail when a dimension is n/a (jargon-free).
NA_REFRAME = "We couldn't measure this from the outside — and that's the point."

# --- Call-to-action (two next steps: understand + fix) --------------------- #
# For now BOTH point at the landing page; a dedicated Masterclass URL slots in
# later. The href is a hardcoded constant — never built from repo data.
CTA_URL = "https://svenroth.ai/shipwright"

CTA_HEADING = "So — what now?"
CTA_LEDE = (
    "The controls greyed out above aren't things you're doing wrong. They're "
    "controls a repo can't prove from the outside. Here are your two next steps."
)
CTA_LEARN_TITLE = "Understand it"
CTA_LEARN_BODY = (
    "Want to actually understand — and control — AI-built code? The Masterclass "
    "explains every one of these controls in plain language, step by step."
)
CTA_LEARN_LINK = "Get the Masterclass →"
CTA_FIX_TITLE = "Fix it"
CTA_FIX_BODY = (
    "Ready to light up the greyed-out controls? Run /shipwright-adopt to bring "
    "your existing repo under control — it proposes the setup as a reviewable "
    "PR, incremental and reversible."
)
CTA_FIX_LINK = "See how adopt works →"
