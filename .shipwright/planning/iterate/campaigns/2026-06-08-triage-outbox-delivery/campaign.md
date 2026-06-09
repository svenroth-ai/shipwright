---
campaign: 2026-06-08-triage-outbox-delivery
status: draft
branch_strategy: stacked
created: 2026-06-08T08:22:25.868727+00:00
expands_triage: trg-94f70926
---

# Campaign: 2026-06-08-triage-outbox-delivery

## Intent

Close the triage.jsonl ORIGIN-DELIVERY gap at its root cause. reconcile_main_triage() folds background drift into chore(triage) commits on LOCAL main; the repo is PR-protected (main never pushed) and worktrees branch from origin/<default>, so those commits are terminal -> local main drifts ahead of origin unbounded and appends never reach origin/CI/fresh-clone. PR #169 solved only J1 (main stays pullable), never J2 (delivery).

Codex review (2026-06-08) KILLED branch-seed+reset (lock-race + abandoned-branch data loss) AND keep-commit+seed (ahead-count still grows unbounded). Root cause is producers writing the tracked main log. Chosen = Option D (re-open the de-scoped C3 reroute), abandoned-branch-safe: gitignored per-tree OUTBOX -> iterate-setup SWEEPS outbox into the PR BRANCH under the canonical lock -> GC drops outbox lines only once they appear in the committed log -> live view reads triage.jsonl UNION outbox for immediacy.

SCOPE = monorepo machinery (D1-D3). The WebUI live-view union is tracked SEPARATELY as a WebUI triage item (the autonomous loop is per-repo; D4 must run in the WebUI repo, not here). The 6-commit backlog was already drained via PR #171. Plan: proposed-triage-reconcile-origin-delivery.md.

## Sub-Iterates

| ID | Slug | Title | Status |
|---|---|---|---|
| D1 | outbox-reroute | Gitignored per-tree outbox + reroute background producers + shared-reader union | pending |
| D2 | sweep-and-gc | Iterate-setup sweep outbox->branch under full lock + delivered-line GC; drop integrate_main reconcile | pending |
| D2V | empirical-verification-gate | EMPIRICAL verification gate — prove D2 loses no triage line (HARD insurance before D3) | pending |
| D3 | scaffold-propagation | Explicit propagation of the outbox path into adopted repos + tests + docs | pending |
