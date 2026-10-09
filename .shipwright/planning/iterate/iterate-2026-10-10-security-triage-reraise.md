# Iterate: security findings reach the Triage (PR 2/2)

Run: `iterate-2026-10-10-security-triage-reraise` - type: bug - complexity: small.

## Problem
Open High security findings were invisible in the Triage while the compliance grade read F. Every GitHub security finding of a repo shared ONE dedup key (`gh-security:<owner>/<repo>`) and the importer's own auto-close was treated as a durable human decision, so one closed item hid every later finding.

## Change
- One card per critical/high finding: `gh-security:<repo>:<cs|art>:<rule>:<path>` (`github_triage/finding_units.py`); the roll-up stays for everything else.
- The importer's own `githubResolved` close of such a card is no longer a durable decision (`triage_defer.is_durable_decision`); human dismissals, the roll-up and other sources (gh-ci, gh-secrets, gh-prompt) keep theirs.
- A failed card pass or a code-scanning outage never closes cards; the artifact feed only fills the gap when no live code-scanning cards exist.
- The import throttle yields to a newer `security.yml` run (one `gh api` call, stored branch).

## Out of scope
No change to `security.yml`; Dependabot stays in the roll-up; prompt-injection mediums unchanged.
