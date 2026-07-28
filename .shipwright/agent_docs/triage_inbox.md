# Triage Inbox

> Auto-generated 2026-07-28T07:58:49.038874Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 447
- Triage: 32 | Promoted: 1 | Dismissed: 413 | Snoozed: 1

## Top 32 items (severity-sorted)

### Source: analysis (1 item)

<a id="trg-57317128"></a>
- **Plugin scope split: entry-point plugins (adopt/grade/run) global, 11 pipeline plugins project-scoped** `id=trg-57317128 | severity=medium | kind=improvement → P2/engineering`
  - Scope the Shipwright marketplace correctly instead of enabling all ~14 plugins at user scope (they currently load /ship…
  - Promote: `triage_promote.py --id trg-57317128 --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-74ef24ce"></a>
- **Compliance: 13 open finding(s)** `id=trg-74ef24ce | severity=high | kind=compliance → P1/compliance`
  - 13 open compliance finding(s): D/D1, D/D3, E/E1, E/E2, E/E3, E/E4, E/E5, E/E?, E/E?, E/E?, F/F6, H/H1, H/H2  - D/D1: Sp…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance
    
    Context: 13 open compliance finding(s): D/D1, D/D3, E/E1, E/E2, E/E3, E/E4, E/E5, E/E?, E/E?, E/E?, F/F6, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-74ef24ce --task-ref EXT:<ref>`

### Source: f0-suite (1 item)

<a id="trg-410ef2a6"></a>
- **[f0] shipwright-run failed in parallel and passed alone - race or flaky test** `id=trg-410ef2a6 | severity=high | kind=bug → P1/engineering`
  - shipwright-run: red in parallel (rc 1), GREEN alone (rc 0). It is NOT xdist-allowlisted, so this is inter-unit pollutio…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --type bug
    
    Context: F0 suite card f0-race:shipwright-run. The test unit shipwright-run failed while the units ran side by side and passed when re-run alone, so the gate stayed green and nothing else recorded it.
    Reproduce alone (expect GREEN): cd plugins/shipwright-run && uv run --with pytest --with pytest-mock pytest tests -q -p no:cacheprovider
    Reproduce in parallel (expect intermittent RED): uv run shared/scripts/tools/run_test_suite.py --project-root 'C:\01_Development\shipwright\.worktrees\security-pyasn1-bump-brace-accept' --run-id iterate-2026-07-28-security-pyasn1-bump-brace-accept
    Establish whether it is a race between units or an unreliable test, fix the cause, and close this card. Never weaken or delete the test to make it pass.
    ```
  - Promote: `triage_promote.py --id trg-410ef2a6 --task-ref EXT:<ref>`

### Source: github (2 items)

<a id="trg-2b5ca5f5"></a>
- **GitHub security: 1 code-scanning + 0 Dependabot (high)** `id=trg-2b5ca5f5 | severity=high | kind=bug → P1/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: 1 high \| dependabot: 0 \| see https://github.com/svenroth-ai/shipwright/…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: GitHub reports 1 open code-scanning finding(s) and 0 open Dependabot alert(s) for svenroth-ai/shipwright.
    Severity breakdown — code-scanning: 1 high; dependabot: 0.
    Live state: https://github.com/svenroth-ai/shipwright/security
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-2b5ca5f5 --task-ref EXT:<ref>`

<a id="trg-8481c271"></a>
- **GitHub prompt-injection: 1 finding(s) (medium)** `id=trg-8481c271 | severity=medium | kind=improvement → P2/engineering`
  - Repo svenroth-ai/shipwright \| prompt-injection (prompt_risks.json): 1 medium \| run: https://github.com/svenroth-ai/sh…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security
    
    Context: the shipwright-security prompt-injection scan reports 1 open finding(s) for svenroth-ai/shipwright.
    Severity breakdown — prompt-injection: 1 medium.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/30276486297
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-prompt:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-8481c271 --task-ref EXT:<ref>`

### Source: iterate (4 items)

<a id="trg-ee7b83e5"></a>
- **Complexity calibration: the history fall-through manufactures medium (79% of runs)** `id=trg-ee7b83e5 | severity=high | kind=bug → P1/engineering`
  - MEASURED 2026-07-28 over 67 recorded runs: 79% classify medium, 16% small, 3% trivial, 1% large. The ladder therefore m…
  - Promote: `triage_promote.py --id trg-ee7b83e5 --task-ref EXT:<ref>`

<a id="trg-2f89afcf"></a>
- **Adopted repos inherit derived-snapshots-off-branch without a refresh producer** `id=trg-2f89afcf | severity=high | kind=improvement → P1/engineering`
  - shared/ syncs into the plugin-cache root that every adopted repo resolves, and the change lives in the iterate skill, s…
  - Promote: `triage_promote.py --id trg-2f89afcf --task-ref EXT:<ref>`

<a id="trg-bd4e75a9"></a>
- **Phase-canon C3 handoff freshness still keys on mtime** `id=trg-bd4e75a9 | severity=low | kind=improvement → P3/engineering`
  - The F11 iterate freshness check moved off filesystem mtime to a content key in iterate-2026-07-27-name-the-blocker (it…
  - Evidence: `shared/scripts/tools/verifiers/common.py`
  - Promote: `triage_promote.py --id trg-bd4e75a9 --task-ref EXT:<ref>`

<a id="trg-d1e466aa"></a>
- **Retire the write-once v1 run-config fields (current_step / completed_steps)** `id=trg-d1e466aa | severity=low | kind=improvement → P3/engineering`
  - Follow-up from iterate-2026-07-14-phase-invocation-mode (external plan review, Gemini #2). The v2 lifecycle never advan…
  - Promote: `triage_promote.py --id trg-d1e466aa --task-ref EXT:<ref>`

### Source: iterate-2026-07-19-compliance-prework (1 item)

<a id="trg-8bf97fd4"></a>
- **S2b: converge the requirement-discovery filter semantics (~10 call-site decisions)** `id=trg-8bf97fd4 | severity=medium | kind=improvement → P2/engineering`
  - The tail of campaign step S2, not a new campaign - file it now so it is not lost between "S2 merged" and "somebody noti…
  - Promote: `triage_promote.py --id trg-8bf97fd4 --task-ref EXT:<ref>`

### Source: manual (15 items)

<a id="trg-d6cc3d3d"></a>
- **Campaign sub-iterates get no internal reviewer cascade — before-merge step at 3f-bis** `id=trg-d6cc3d3d | severity=high | kind=improvement → P1/engineering`
  - The sub-iterate-runner has no Agent tool and delegates the internal cascade to the campaign orchestrator, but the auton…
  - Promote: `triage_promote.py --id trg-d6cc3d3d --task-ref EXT:<ref>`

<a id="trg-9e2ce202"></a>
- **PR review: a fail-closed verdict outlives its cause and blocks the PR forever** `id=trg-9e2ce202 | severity=high | kind=bug → P1/engineering`
  - When the Tier-3 reviewer fails closed (diff truncation, unparsable model reply), it posts a CHANGES_REQUESTED review. W…
  - Promote: `triage_promote.py --id trg-9e2ce202 --task-ref EXT:<ref>`

<a id="trg-51f8e2a1"></a>
- **deferring a triage finding does not yet defer it - make the third decision mean what it says** `id=trg-51f8e2a1 | severity=high | kind=improvement → P1/engineering`
  - Post-merge review of PR #444 found the CLI defer subcommand records the decision correctly but almost nothing downstrea…
  - Promote: `triage_promote.py --id trg-51f8e2a1 --task-ref EXT:<ref>`

<a id="trg-2ca796f3"></a>
- **Release aggregator can write the same version twice on a re-run** `id=trg-2ca796f3 | severity=high | kind=bug → P1/engineering`
  - aggregate_changelog.py is the writer the release path actually invokes (changelog SKILL.md Step 4). _insert_section alw…
  - Evidence: `.shipwright/planning/iterate/iterate-2026-07-27-changelog-writer-preserve-history.md`
  - Promote: `triage_promote.py --id trg-2ca796f3 --task-ref EXT:<ref>`

<a id="trg-51a57370"></a>
- **F11 review floor accepts an evidence-free row, and skips entirely when the iterate entry is missing** `id=trg-51a57370 | severity=medium | kind=bug → P2/engineering`
  - Two pre-existing fail-open paths in check_review_record, demonstrated by the Stage-3 doubt pass on iterate-2026-07-28-c…
  - Promote: `triage_promote.py --id trg-51a57370 --task-ref EXT:<ref>`

<a id="trg-64372769"></a>
- **Review record cannot evidence Stage 1 (spec-reviewer) — add a spec review type** `id=trg-64372769 | severity=medium | kind=improvement → P2/engineering`
  - REVIEW_TYPES has no 'spec' entry, so the spec-compliance HARD-GATE has no row. After iterate-2026-07-28-cascade-delegat…
  - Promote: `triage_promote.py --id trg-64372769 --task-ref EXT:<ref>`

<a id="trg-72a9d195"></a>
- **grade_snapshot has no branch/commit attribution: the Grade-Trend timeline mixes divergent trees** `id=trg-72a9d195 | severity=medium | kind=bug → P2/engineering`
  - grade_snapshot events carry grade + score but nothing that identifies WHICH tree they were measured in. The emitter omi…
  - Promote: `triage_promote.py --id trg-72a9d195 --task-ref EXT:<ref>`

<a id="trg-f2d69527"></a>
- **An unreadable run config silently demotes a driven run to standalone, disabling the override guarantee** `id=trg-f2d69527 | severity=medium | kind=bug → P2/engineering`
  - Deferred from iterate-2026-07-27-handoff-tally-and-gate-honesty (PR #468); found by its Stage-3 doubt review and record…
  - Evidence: `.shipwright/planning/adr/114-report-what-will-exist-not-what-exists-yet.md`
  - Promote: `triage_promote.py --id trg-f2d69527 --task-ref EXT:<ref>`

<a id="trg-2ea0b99a"></a>
- **Cross-layer gate cannot see a behaviour change that adds criteria under an unchanged FR row** `id=trg-2ea0b99a | severity=medium | kind=improvement → P2/engineering`
  - The cross-layer coverage check keys 'did behaviour change?' on a changed FR TABLE ROW. The standing campaign rule is th…
  - Promote: `triage_promote.py --id trg-2ea0b99a --task-ref EXT:<ref>`

<a id="trg-ecddb31f"></a>
- **update-marketplace reports up-to-date for a plugin the sync checker calls drifted** `id=trg-ecddb31f | severity=medium | kind=improvement → P2/engineering`
  - Discovered while syncing the runtime cache after iterate-2026-07-27-requirement-writeback-loop; unrelated to that chang…
  - Promote: `triage_promote.py --id trg-ecddb31f --task-ref EXT:<ref>`

<a id="trg-93ceb2b0"></a>
- **a triage decision can be silently lost and the command still reports success** `id=trg-93ceb2b0 | severity=medium | kind=bug → P2/engineering`
  - Found by adversarial review of PR #444; pre-existing, shared by all three decisions (promote, dismiss, defer), not intr…
  - Promote: `triage_promote.py --id trg-93ceb2b0 --task-ref EXT:<ref>`

<a id="trg-9862202d"></a>
- **host checks part 2 follow-up: require the checks that currently gate nothing** `id=trg-9862202d | severity=medium | kind=improvement → P2/engineering`
  - FOLLOW-UP to trg-c7e5835b, do this AFTER the part-2 PR (items 3-5) is merged. The new check_required_checks producer fo…
  - Promote: `triage_promote.py --id trg-9862202d --task-ref EXT:<ref>`

<a id="trg-80e3b3cd"></a>
- **No CI job runs on Windows, so platform-specific defects and fixes are unverified** `id=trg-80e3b3cd | severity=medium | kind=improvement → P2/engineering`
  - Every workflow in .github/workflows runs on ubuntu-latest, so no CI job ever executes on Windows. Two consequences obse…
  - Promote: `triage_promote.py --id trg-80e3b3cd --task-ref EXT:<ref>`

<a id="trg-0a294ef3"></a>
- **A successful atomic-write retry is silent, so degrading contention is unobservable** `id=trg-0a294ef3 | severity=medium | kind=improvement → P2/engineering`
  - shared/scripts/lib/atomic_write.py retries a Windows sharing violation on both the write and the read side. A retry tha…
  - Promote: `triage_promote.py --id trg-0a294ef3 --task-ref EXT:<ref>`

<a id="trg-c6e75011"></a>
- **shipwright-security tests write an untracked .shipwright/ dir into the repo tree** `id=trg-c6e75011 | severity=low | kind=bug → P3/engineering`
  - Running the F0 suite leaves an untracked directory in the working tree: plugins/shipwright-security/.shipwright/ contai…
  - Promote: `triage_promote.py --id trg-c6e75011 --task-ref EXT:<ref>`

### Source: req3-campaign (3 items)

<a id="trg-137f48b5"></a>
- **REQ3.05 [CAMPAIGN AUTONOM] Test-Backfill: fehlende AC-Tests - Monorepo** `id=trg-137f48b5 | severity=medium | kind=improvement → P2/engineering`
  - Der Coverage-Motor, eigener Anker damit er nicht nachgeschleift wird. Schreibt Tests fuer ACs, die heute keinen beweise…
  - Promote: `triage_promote.py --id trg-137f48b5 --task-ref EXT:<ref>`

<a id="trg-b5bd4a0a"></a>
- **REQ3.10 [ITERATE] Grader Lead-Magnet: change_reconciliation real machen** `id=trg-b5bd4a0a | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv. Der Grader reserviert change_reconciliation bereits als 'Shipwright-only'-Dimension (kappt kalte R…
  - Promote: `triage_promote.py --id trg-b5bd4a0a --task-ref EXT:<ref>`

<a id="trg-7085d783"></a>
- **REQ3.04 [CAMPAIGN AUTONOM] Mechanik - Monorepo** `id=trg-7085d783 | severity=medium | kind=improvement → P2/engineering`
  - Phase 3, AUTONOME Kampagne. Sub-Iterates: Evidenzkette (CI regeneriert Manifest, muss matchen), AC-Identitaet, Manifest…
  - Promote: `triage_promote.py --id trg-7085d783 --task-ref EXT:<ref>`

### Source: req3-granularity-round (1 item)

<a id="trg-1d7d91d0"></a>
- **Spec-coherence check S5 is blind to the converged acceptance-criteria shape** `id=trg-1d7d91d0 | severity=medium | kind=bug → P2/engineering`
  - check_s5_fr_coherence reports every requirement in this repo's own catalogue as missing both description and acceptance…
  - Evidence: `.shipwright/planning/iterate/2026-07-27-project-granularity-basis.md`
  - Promote: `triage_promote.py --id trg-1d7d91d0 --task-ref EXT:<ref>`

### Source: req3-phase2-walk (3 items)

<a id="trg-b95ab887"></a>
- **REQ3.06 [CAMPAIGN AUTONOM] Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only (mechanisable) - Monorepo** `id=trg-b95ab887 | severity=high | kind=improvement → P1/engineering`
  - AUTONOME Kampagne. Der Anker, der die Enforcement-Liste des AC-Nachweis-Registers abarbeitet - das Register IST die Arb…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-b95ab887 --task-ref EXT:<ref>`

<a id="trg-c7e5835b"></a>
- **host checks: gates that gate nothing, plus the verdict label (supersedes trg-2f9865fb)** `id=trg-c7e5835b | severity=high | kind=improvement → P1/engineering`
  - OWNS: everything under the workflows directory, the shipped workflow templates, and the must-pass-check derivation help…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-c7e5835b --task-ref EXT:<ref>`

<a id="trg-e9fa7c49"></a>
- **REQ3.09 [ITERATE] Domaenen-Glossar erzeugen, Grill-Modul in Project, plus die Nachweis-Spur (supersedes trg-d5522f68)** `id=trg-e9fa7c49 | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv, Follow-up nach der Kampagne. OWNS: die Elicitation-Oberflaeche von PROJECT, das geteilte Grill-Mod…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-e9fa7c49 --task-ref EXT:<ref>`

