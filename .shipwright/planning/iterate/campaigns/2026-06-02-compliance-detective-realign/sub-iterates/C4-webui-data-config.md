# C4 — webui data + config reconcile (G2 stoplist + reopen FR link)

- **Type:** change (project data/config — NOT framework)
- **Complexity:** trivial → small
- **Repo:** **shipwright-webui** (NOT the monorepo)
- **Depends on:** C1 + C2 merged into the monorepo **and**
  `bash scripts/update-marketplace.sh` run (so the webui's cached plugin runs
  the realigned logic)
- **Closes:** G2 of `trg-2bce4cc6`; D5 (data side)

## Problem

Two webui-local residuals that are genuine project data/config, not framework
bugs — but which must be fixed in the webui repo **after** the monorepo realign
lands, or they get re-flagged / masked:

- **G2:** conventional-commit scope `board` (commit `26ea506`) is not in the
  webui `audit_config.g2_stoplist`. It is a legitimate component scope.
- **D5 (data):** the reopen feature event `evt-83b9b73f`
  (`POST /api/external/tasks/:id/reopen`) records `spec_impact=ADD` but links no
  FR. The endpoint has a real spec footprint, so it should reference the correct
  FR (reaffirm an existing FR, or `new_frs` if it introduced one) — not be
  marked `spec_impact=none`.

## Why last / why a separate sub-iterate

The webui background producer audits via the **cached** plugin. C1 (B7 Run-ID
linkage) and C2 (A5 invocation) only reach the webui after they merge and
`update-marketplace.sh` syncs. Doing C4 earlier means: G2 stays correct but
B7/A5.0 would still mis-fire, and a re-audit could re-open items. Land the
framework realign first, sync, then reconcile the webui's own data.

## Acceptance Criteria

- [ ] **AC-1 (G2).** `board` added to the webui `audit_config.json`
      `g2_stoplist`; re-audit reports G2 green. (Consider whether C1's optional
      scope-derivation makes the manual entry unnecessary — if shipped, skip the
      manual add.)
- [ ] **AC-2 (D5 data).** The reopen event is amended (via the supported
      `event_amended` correction path — see `iterate-2026-06-01-audit-honors-amendments`)
      to link its correct FR; re-audit reports D5 green.
- [ ] **AC-3 (clean re-audit).** With C1–C3 synced, a fresh webui detective audit
      shows A5/B7/D3/D5/G2 all green/skip — `trg-2bce4cc6` auto-dismisses.

## Risk / care

- Use the **amendment** path for the event, not a hand-edit of `events.jsonl`
  (preserves the append-only audit trail and is what the D-group honors).
- Confirm the reopen endpoint's true FR before linking — do not invent one to
  silence D5.
