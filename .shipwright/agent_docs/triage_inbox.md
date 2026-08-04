# Triage Inbox

> Auto-generated 2026-08-04T07:03:55.549555Z. Items waiting for triage decision.
> Promote via WebUI Triage tab (when v1b lands) or `shared/scripts/tools/triage_promote.py --id <id> --task-ref EXT:<ref>`.

## Status summary

- Total: 618
- Triage: 40 | Promoted: 2 | Dismissed: 573 | Snoozed: 3

## Top 40 items (severity-sorted)

### Source: board-split (15 items)

<a id="trg-66cb695e"></a>
- **P2.18 \[GUIDED\] Adopted repos need current evidence, scope shrank after Weg B** `id=trg-66cb695e | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-515060a6, whose text says 'do not start before the architecture decision falls'. It has fallen: Weg B is…
  - Promote: `triage_promote.py --id trg-66cb695e --task-ref EXT:<ref>`

<a id="trg-210fde7b"></a>
- **P3.05 \[SERIAL 5/6 after P3.04\] No CI job runs on Windows** `id=trg-210fde7b | severity=high | kind=improvement → P1/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-210fde7b --task-ref EXT:<ref>`

<a id="trg-faa3857c"></a>
- **P2.17 \[GUIDED\] No review pass asks whether the architecture is the right one** `id=trg-faa3857c | severity=high | kind=improvement → P1/engineering`
  - Split out of anchor trg-fc173418 \(7a delivered, 7b delivered PR #514, 7d is trg-e4156151\). The cascade checks the dif…
  - Promote: `triage_promote.py --id trg-faa3857c --task-ref EXT:<ref>`

<a id="trg-0bb180f6"></a>
- **P2.30 \[SERIAL after P2.26\] F11 refuses a previous-run fallback when current evidence is unreadable** `id=trg-0bb180f6 | severity=medium | kind=bug → P2/engineering`
  - SUPERSEDES trg-e0a0f569 and preserves its measured finding. spec\_checks.\_read\_iterate\_entry and iterate\_compliance…
  - Promote: `triage_promote.py --id trg-0bb180f6 --task-ref EXT:<ref>`

<a id="trg-2c958bad"></a>
- **P2.29 \[AUTO\] Cross-plugin mirror tree joins the cache drift check** `id=trg-2c958bad | severity=medium | kind=improvement → P2/engineering`
  - SUPERSEDES trg-5005bf57 and preserves its scope. P1.07 and P1.08 are delivered, so this is now unblocked. The plugin ca…
  - Promote: `triage_promote.py --id trg-2c958bad --task-ref EXT:<ref>`

<a id="trg-1c9edf88"></a>
- **P4.01 \[AUTO after P1.01\] Nothing enforces that F5c records the re-checked complexity** `id=trg-1c9edf88 | severity=medium | kind=improvement → P2/engineering`
  - SUPERSEDES trg-da9320d8 - same content, placed in the phase scheme. Found by the doubt-review of iterate-2026-08-01-cam…
  - Promote: `triage_promote.py --id trg-1c9edf88 --task-ref EXT:<ref>`

<a id="trg-25ecd3cd"></a>
- **P3.06 \[SERIAL 6/6 after P3.05, BLOCKED on trg-e4156151\] Tier exempts maintainer PRs from authorship** `id=trg-25ecd3cd | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-25ecd3cd --task-ref EXT:<ref>`

<a id="trg-abd0a247"></a>
- **P3.04 \[SERIAL 4/6 after P3.03\] The security gate reports a blank pass while high findings are open** `id=trg-abd0a247 | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-abd0a247 --task-ref EXT:<ref>`

<a id="trg-14d46892"></a>
- **P3.02 \[SERIAL 2/6 after P3.01\] Fork PRs get no model review, the host withholds credentials** `id=trg-14d46892 | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-14d46892 --task-ref EXT:<ref>`

<a id="trg-569bc60b"></a>
- **P3.01 \[SERIAL 1/6\] The scaffolded reviewer skips large changes instead of failing closed** `id=trg-569bc60b | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-569bc60b --task-ref EXT:<ref>`

<a id="trg-8b5f8f40"></a>
- **P2.16 \[GUIDED\] An unreadable run config reads as standalone** `id=trg-8b5f8f40 | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-040223fe. \_read\_standalone\_flag treats an unparseable config like a missing one and answers…
  - Promote: `triage_promote.py --id trg-8b5f8f40 --task-ref EXT:<ref>`

<a id="trg-5b45c165"></a>
- **P2.19 \[GUIDED\] Remaining IT-1 audit findings 14 and 20-29** `id=trg-5b45c165 | severity=medium | kind=improvement → P2/engineering`
  - Split out of anchor trg-4ebc928e, which is now closed. These were deliberately kept in the anchor rather than filed as…
  - Promote: `triage_promote.py --id trg-5b45c165 --task-ref EXT:<ref>`

<a id="trg-095cd2bf"></a>
- **P2.20 \[GUIDED\] Accepted-risk register: should it gain a schema field** `id=trg-095cd2bf | severity=low | kind=improvement → P3/engineering`
  - SUPERSEDES trg-87174b37 - retitled into the phase scheme, content unchanged \(full text on the original\). Monorepo onl…
  - Promote: `triage_promote.py --id trg-095cd2bf --task-ref EXT:<ref>`

<a id="trg-01cd6aef"></a>
- **P2.15 \[GUIDED\] F11 handoff freshness and the derived-snapshot gate contradict** `id=trg-01cd6aef | severity=low | kind=bug → P3/engineering`
  - SUPERSEDES trg-758e62c0 - retitled into the phase scheme, content unchanged \(full text on the original\). Pairs with P…
  - Promote: `triage_promote.py --id trg-01cd6aef --task-ref EXT:<ref>`

<a id="trg-a089c9f7"></a>
- **P3.03 \[SERIAL 3/6 after P3.02\] The must-pass set is never compared against the checks that exist** `id=trg-a089c9f7 | severity=low | kind=improvement → P3/engineering`
  - Split out of anchor trg-bd66b9b0. IT-9 owns EVERY file under .github/workflows/ exclusively, so all six IT-9 units are…
  - Promote: `triage_promote.py --id trg-a089c9f7 --task-ref EXT:<ref>`

### Source: code-review (1 item)

<a id="trg-cab3306e"></a>
- **P2.28 \[AUTO after P2.05\] record\_event by-commit dedup is not type-scoped, unlike the grade branch** `id=trg-cab3306e | severity=low | kind=bug → P3/engineering`
  - append\_event\_idempotent's deduplicate\_by\_commit branch is gated only on the presence of a commit field and consults…
  - Promote: `triage_promote.py --id trg-cab3306e --task-ref EXT:<ref>`

### Source: compliance (1 item)

<a id="trg-6783c9e6"></a>
- **Compliance: 5 open finding\(s\)** `id=trg-6783c9e6 | severity=high | kind=compliance → P1/compliance`
  - 5 open compliance finding\(s\): D/D1, D/D3, F/F6, H/H1, H/H2  - D/D1: Spec FR coverage in events — uncovered FRs — Shou…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-compliance

    Context: 5 open compliance finding(s): D/D1, D/D3, F/F6, H/H1, H/H2.
    Dashboard: .shipwright/compliance/dashboard.md
    Each finding + hint is listed in this item's detail.
    ```
  - Promote: `triage_promote.py --id trg-6783c9e6 --task-ref EXT:<ref>`

### Source: doubt-review (1 item)

<a id="trg-97aeaede"></a>
- **Align WebUI and Python triage transition locking** `id=trg-97aeaede | severity=high | kind=bug → P1/engineering`
  - shipwright-webui uses proper-lockfile while Python triage uses the shared FileLock, so concurrent terminal decisions ar…
  - Promote: `triage_promote.py --id trg-97aeaede --task-ref EXT:<ref>`

### Source: doubt-review-followup (1 item)

<a id="trg-06641ec3"></a>
- **Runtime verifier should bind PID liveness to process identity** `id=trg-06641ec3 | severity=medium | kind=improvement → P2/engineering`
  - Numeric PID liveness is best-effort and can accept a replacement process after PID reuse. A complete fix needs a produc…
  - Promote: `triage_promote.py --id trg-06641ec3 --task-ref EXT:<ref>`

### Source: doubt-reviewer (1 item)

<a id="trg-486cb11c"></a>
- **P2.27 \[GUIDED after P2.08\] Decide how verify\_local.py gets run: pre-push hook, F0 step, or manual** `id=trg-486cb11c | severity=medium | kind=improvement → P2/engineering`
  - verify\_local.py mirrors ci.yml's three bespoke merge guards locally, but nothing invokes it: no hook, no SKILL.md step…
  - Promote: `triage_promote.py --id trg-486cb11c --task-ref EXT:<ref>`

### Source: f0-suite (1 item)

<a id="trg-c31bd693"></a>
- **\[f0\] integration-tests failed in parallel and passed alone - race or flaky test** `id=trg-c31bd693 | severity=high | kind=bug → P1/engineering`
  - integration-tests: red in parallel \(rc 1\), GREEN alone \(rc 0\). It IS on the suite.xdist allowlist, so the fan-out i…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --type bug

    Context: F0 suite card f0-race:integration-tests. The test unit integration-tests failed while the units ran side by side and passed when re-run alone, so the gate stayed green and nothing else recorded it.
    Reproduce alone (expect GREEN): uv run --python 3.11 --with pytest --with pytest-mock --with pytest-cov pytest integration-tests -q -p no:cacheprovider --cov=shared '--cov-config=C:\01_Development\shipwright\.worktrees\p1-15-events-context\pyproject.toml' --cov-report=
    Reproduce in parallel (expect intermittent RED): uv run --python 3.11 shared/scripts/tools/run_test_suite.py --project-root 'C:\01_Development\shipwright\.worktrees\p1-15-events-context' --run-id iterate-2026-08-04-p1-15-events-context
    Establish whether it is a race between units or an unreliable test, fix the cause, and close this card. Never weaken or delete the test to make it pass.
    ```
  - Promote: `triage_promote.py --id trg-c31bd693 --task-ref EXT:<ref>`

### Source: fleet-resource-audit (2 items)

<a id="trg-7b7aa280"></a>
- **P1.12 \[AUTO after P1.11\]\[FLEET-BLOCKER\]\[SERIAL\] Share the host CPU budget across sibling-worktree F0 runs** `id=trg-7b7aa280 | severity=high | kind=bug → P1/engineering`
  - F0 limits only one invocation: on this 24-logical-CPU Windows host each worktree derives cpu\_count-2 = 22 slots, while…
  - Promote: `triage_promote.py --id trg-7b7aa280 --task-ref EXT:<ref>`

<a id="trg-fab34aa0"></a>
- **P2.32 \[AUTO after P1.12\]\[PARALLEL WITH OTHER P2\] Stream F0 progress and clean up interrupted Windows process trees** `id=trg-fab34aa0 | severity=medium | kind=improvement → P2/engineering`
  - F0 currently capture-buffers every unit and prints the report only after the entire pool and retries finish, so Codex o…
  - Promote: `triage_promote.py --id trg-fab34aa0 --task-ref EXT:<ref>`

### Source: github (3 items)

<a id="trg-854eaff3"></a>
- **\[ci\] CI failing on main** `id=trg-854eaff3 | severity=high | kind=bug → P1/engineering`
  - Workflow 'CI' last concluded 'failure' on main@64c8c33 \| latest run: https://github.com/svenroth-ai/shipwright/actions…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-iterate --type bug

    Context: GitHub Actions workflow 'CI' is failing on the default branch (main) in svenroth-ai/shipwright.
    Last conclusion: failure.
    Live workflow history: https://github.com/svenroth-ai/shipwright/actions/workflows/259825682
    Source: triage item gh-ci:259825682
    ```
  - Promote: `triage_promote.py --id trg-854eaff3 --task-ref EXT:<ref>`

<a id="trg-c8d81fd7"></a>
- **GitHub prompt-injection: 1 finding\(s\) \(high\)** `id=trg-c8d81fd7 | severity=high | kind=bug → P1/engineering`
  - Repo svenroth-ai/shipwright \| prompt-injection \(prompt\_risks.json\): 1 high \| run: https://github.com/svenroth-ai/s…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security

    Context: the shipwright-security prompt-injection scan reports 1 open finding(s) for svenroth-ai/shipwright.
    Severity breakdown — prompt-injection: 1 high.
    Workflow run: https://github.com/svenroth-ai/shipwright/actions/runs/30638995806
    Re-scan locally: see docs/security-ci-setup.md
    Source: triage item gh-prompt:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-c8d81fd7 --task-ref EXT:<ref>`

<a id="trg-d644045a"></a>
- **GitHub security: 2 code-scanning + 0 Dependabot \(low\)** `id=trg-d644045a | severity=low | kind=improvement → P3/engineering`
  - Repo svenroth-ai/shipwright \| code-scanning: 2 low \| dependabot: 0 \| see https://github.com/svenroth-ai/shipwright/s…
  - Launch payload (copy into a new Claude session):
    ```text
    /shipwright-security

    Context: GitHub reports 2 open code-scanning finding(s) and 0 open Dependabot alert(s) for svenroth-ai/shipwright.
    Severity breakdown — code-scanning: 2 low; dependabot: 0.
    Live state: https://github.com/svenroth-ai/shipwright/security
    Source: triage item gh-security:svenroth-ai/shipwright
    ```
  - Promote: `triage_promote.py --id trg-d644045a --task-ref EXT:<ref>`

### Source: iterate (2 items)

<a id="trg-4183acd3"></a>
- **P2.26 \[AUTO after P2.22\] \_git\_available still uses the binary probe, so five callers keep the conflation** `id=trg-4183acd3 | severity=medium | kind=bug → P2/engineering`
  - FOUND BY the Stage-3 doubt review of iterate-2026-08-01-fail-closed-reader-migration; the natural next card in the same…
  - Promote: `triage_promote.py --id trg-4183acd3 --task-ref EXT:<ref>`

<a id="trg-18da39b0"></a>
- **P2.24 \[AUTO after P1.07+P1.08\] Version ordering treats a SemVer prerelease as newer than its release** `id=trg-18da39b0 | severity=low | kind=bug → P3/engineering`
  - Both scripts/cache\_tree\_compare.version\_key and its stdlib-only mirror in the ensure\_shared\_cache hook parse the l…
  - Evidence: `scripts/cache_tree_compare.py`
  - Promote: `triage_promote.py --id trg-18da39b0 --task-ref EXT:<ref>`

### Source: iterate-2026-08-01-drop-write-once-step-fields (1 item)

<a id="trg-8d52a965"></a>
- **Retire the write-once current\_step / completed\_steps fields \(campaign, not a P3 unit\)** `id=trg-8d52a965 | severity=medium | kind=improvement → P2/engineering`
  - Successor to trg-be24ff6f, which asked to migrate two phase\_quality readers to phase\_tasks\[\] and 'then drop the fie…
  - Promote: `triage_promote.py --id trg-8d52a965 --task-ref EXT:<ref>`

### Source: iterate-2026-08-01-grade-snapshot-dirty-capture (1 item)

<a id="trg-709828ad"></a>
- **P4.02 \[GUIDED\] grade\_snapshot dirty: the orchestrator's sibling-process residual** `id=trg-709828ad | severity=low | kind=improvement → P3/engineering`
  - Left open deliberately by iterate-2026-08-01-grade-snapshot-dirty-capture, which shipped grade\_snapshot.dirty captured…
  - Promote: `triage_promote.py --id trg-709828ad --task-ref EXT:<ref>`

### Source: manual (1 item)

<a id="trg-65b6d918"></a>
- **P1.15 \[AUTO\]\[PARALLEL\] Replace full iterate startup read of shipwright\_events.jsonl with bounded relevant context** `id=trg-65b6d918 | severity=high | kind=improvement → P1/engineering`
  - ONE ACTION-UNIT Implement the complete relevance-bounded LLM access path for shipwright\_events.jsonl in one iterate. T…
  - Evidence: `Spec/context-cost-report.md`
  - Promote: `triage_promote.py --id trg-65b6d918 --task-ref EXT:<ref>`

### Source: operator-review-cost-policy (1 item)

<a id="trg-af3e0872"></a>
- **P2.33 \[AUTO now\]\[COMBINES P2.21\]\[FINAL F0 after P1.12\] Replace Gemini review arm with ZDR-routed DeepSeek V4 Pro** `id=trg-af3e0872 | severity=high | kind=improvement → P1/engineering`
  - Operator decision: KEEP the GPT review arm on gpt-5.6-terra / openai/gpt-5.6-terra. Replace the default Gemini arm with…
  - Promote: `triage_promote.py --id trg-af3e0872 --task-ref EXT:<ref>`

### Source: req3-campaign (3 items)

<a id="trg-c396f7d8"></a>
- **REQ3.04 \[CAMPAIGN AUTONOM\] Mechanik Monorepo plus der Spec-Reader \(supersedes trg-7085d783\)** `id=trg-c396f7d8 | severity=high | kind=improvement → P1/engineering`
  - SUPERSEDES trg-7085d783, KONSOLIDIERT zusaetzlich trg-1d7d91d0 + trg-2ea0b99a + trg-8bf97fd4. Owner-Entscheidung 2026-0…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-c396f7d8 --task-ref EXT:<ref>`

<a id="trg-137f48b5"></a>
- **REQ3.05 \[CAMPAIGN AUTONOM\] Test-Backfill: fehlende AC-Tests - Monorepo** `id=trg-137f48b5 | severity=medium | kind=improvement → P2/engineering`
  - Der Coverage-Motor, eigener Anker damit er nicht nachgeschleift wird. Schreibt Tests fuer ACs, die heute keinen beweise…
  - Promote: `triage_promote.py --id trg-137f48b5 --task-ref EXT:<ref>`

<a id="trg-b5bd4a0a"></a>
- **REQ3.10 \[ITERATE\] Grader Lead-Magnet: change\_reconciliation real machen** `id=trg-b5bd4a0a | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv. Der Grader reserviert change\_reconciliation bereits als 'Shipwright-only'-Dimension \(kappt kalte…
  - Promote: `triage_promote.py --id trg-b5bd4a0a --task-ref EXT:<ref>`

### Source: req3-phase2-walk (2 items)

<a id="trg-b95ab887"></a>
- **REQ3.06 \[CAMPAIGN AUTONOM\] Enforcement-Liste abarbeiten: Checks bauen fuer prompt-only \(mechanisable\) - Monorepo** `id=trg-b95ab887 | severity=high | kind=improvement → P1/engineering`
  - AUTONOME Kampagne. Der Anker, der die Enforcement-Liste des AC-Nachweis-Registers abarbeitet - das Register IST die Arb…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-b95ab887 --task-ref EXT:<ref>`

<a id="trg-e9fa7c49"></a>
- **REQ3.09 \[ITERATE\] Domaenen-Glossar erzeugen, Grill-Modul in Project, plus die Nachweis-Spur \(supersedes trg-d5522f68…** `id=trg-e9fa7c49 | severity=medium | kind=improvement → P2/engineering`
  - Phase 4, interaktiv, Follow-up nach der Kampagne. OWNS: die Elicitation-Oberflaeche von PROJECT, das geteilte Grill-Mod…
  - Evidence: `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md`
  - Promote: `triage_promote.py --id trg-e9fa7c49 --task-ref EXT:<ref>`

### Source: test-evidence-followup (1 item)

<a id="trg-dbb83bb0"></a>
- **P1.14 \[AUTO after P1.12\]\[PARALLEL\] Recover post-backfill immutable test evidence from retained worktrees** `id=trg-dbb83bb0 | severity=high | kind=bug → P1/engineering`
  - Close the transition gap around P1.11 before deleting retained worktrees. Recover exact bytes only for two now-delivere…
  - Promote: `triage_promote.py --id trg-dbb83bb0 --task-ref EXT:<ref>`

### Source: triage-consolidation-2026-07-28 (1 item)

<a id="trg-66b45477"></a>
- **IT-10 Plugin-Scope-Split: Einstiegs-Plugins global, 11 Pipeline-Plugins projekt-scoped** `id=trg-66b45477 | severity=medium | kind=improvement → P2/engineering`
  - SUPERSEDES trg-57317128 - inhaltlich unveraendert, nur in das IT-Schema umbenannt, damit das Board einheitlich ist. Spe…
  - Evidence: `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md`
  - Promote: `triage_promote.py --id trg-66b45477 --task-ref EXT:<ref>`

### Source: webui-cross-repo (1 item)

<a id="trg-3e49151c"></a>
- **\[P2.31\]\[AUTO after P1.11\]\[PARALLEL\] Accept string-shaped iterate test status in build-dashboard regen** `id=trg-3e49151c | severity=high | kind=bug → P1/engineering`
  - MOVED from shipwright-webui trg-cb7d4938. F5b build-dashboard regeneration fails on WebUI iterates because shared/scrip…
  - Promote: `triage_promote.py --id trg-3e49151c --task-ref EXT:<ref>`

## Deferred — decided, revisit later (3)

_Not gone: each of these was decided, with a date it comes back on._

- **The delivery ladder's self-merge rung has never run against a real unprotected repository** `id=trg-5c62fa56 | severity=medium | revisit=(no revisit date recorded)`
  - Reason: Re-homed to trg-a678bd00 \(Adopt Automerge-Readiness\). Rung 3 is unreachable here: main is protected and self-merge on…
  - Un-park: `triage_cli.py unpark trg-5c62fa56 --reason <why>`

- **Changelog aggregator does not preserve BOM / line endings the plugin writer preserves** `id=trg-239ee0ad | severity=low | revisit=(no revisit date recorded)`
  - Reason: P3, in PR #472 bewusst akzeptiert und an zwei Stellen dokumentiert \(Modul-Docstring changelog\_splice.py + Iterate-Spe…
  - Un-park: `triage_cli.py unpark trg-239ee0ad --reason <why>`

- **Plugin cache may be out of sync after plugin-side edits** `id=trg-e60d7ddd | severity=low | revisit=(no revisit date recorded)`
  - Reason: (no reason recorded)
  - Un-park: `triage_cli.py unpark trg-e60d7ddd --reason <why>`

