# Handover — Empirical Verification of Artifact-Polish Campaign (B.2 → C.3)

> **For a fresh Claude Code session.** Read this from disk at
> `c:/01_Development/shipwright/.shipwright/planning/campaigns/2026-05-21-artifact-polish-empirical-verification.md`
> or have the operator paste it. The campaign-state file at
> `2026-05-21-artifact-polish-completion-state.md` records what was
> built; THIS handover instructs you to verify it actually works
> end-to-end against real repos.

---

## Why this handover exists

The artifact-polish campaign shipped six iterates (B.2 → C.3) under
PRs #57-#62, all merged to `main` on 2026-05-21. The previous session
ran unit + integration tests and validated marketplace sync, but did
NOT verify that each iterate produces visible, operator-facing output
on the two real repos that consume the plugins:

1. `c:/01_Development/shipwright/` — the monorepo itself (greenfield).
2. `c:/01_Development/shipwright-webui/` — adopted via `/shipwright-adopt`,
   carries known-bloated artifacts (`CLAUDE.md` ~270 lines, historical
   stale FAIL RTM rows, possibly bloated ADRs).

The user explicitly called out: "Ich möchte dass du alles was du
gerade gemacht hast empirisch testest. Im shipwright repo und im
webui repo. Sonst bringt doch das nichts." Translation: every iterate
must produce visible, real-data effect on BOTH repos, or it doesn't
ship. Tests passing is necessary, not sufficient.

A known gap surfaced before this handover was written:

- **B.4 deep-link rendering has zero visible effect on either repo
  today** because no producer in the campaign sets the `frId` field
  on triage items (B.2 SBOM is per-workspace, B.3 test-evidence is
  per-layer — neither has FR context). The infrastructure works
  (24 unit tests pass), but the live RTM never shows a `FAIL →
  trg-XXX` deep-link.

Your job: empirically verify each iterate, document what's visible
and what's not, and either close the gaps OR write them up as
follow-up work the operator must approve. Don't ship "tests pass"
as verification.

---

## Squash commits to verify (already merged on `main`)

| Iterate | PR  | Squash    | ADR     | Headline                                                |
|---------|-----|-----------|---------|---------------------------------------------------------|
| B.2     | #57 | `47ab03d` | ADR-056 | SBOM undeclared-license triage (per workspace)          |
| B.3     | #58 | `ccb2b98` | ADR-057 | test-evidence Layer column + per-layer FAIL triage     |
| B.4     | #59 | `48024b1` | ADR-058 | RTM `FAIL → trg-XXX` deep-link + Coverage Summary      |
| C.1     | #60 | `388fa55` | ADR-059 | Hard-enforce FR-or-change-type gate at iterate finalize |
| C.2     | #61 | `9008cf4` | ADR-060 | Doc-hygiene audit detectors (F4-F7)                     |
| C.3     | #62 | `02eb08a` | ADR-061 | Plugin-cache vs repo drift detector                     |
| (docs)  | #63 | `d27a889` | —       | Campaign state file finalization                        |

All long-form rationale + reviewer dispositions live in
`.shipwright/planning/adr/056-061-*.md`.

---

## Setup checklist (run once before testing)

```bash
# 1. Sync the monorepo (you'll be testing against `main` HEAD).
cd c:/01_Development/shipwright
git status --short    # should be clean except auto-regen artifacts
git pull --ff-only origin main
git log --oneline -8   # confirm d27a889 + 02eb08a + 9008cf4 + 388fa55 + 48024b1 + ccb2b98 + 47ab03d

# 2. Confirm the marketplace cache is fresh (run from monorepo).
bash scripts/update-marketplace.sh 2>&1 | tail -10
# Expect: "13 synced, 0 skipped, 0 errors"

# 3. Confirm webui repo is accessible.
cd c:/01_Development/shipwright-webui
git status --short
git log --oneline -3
ls -la .shipwright/

# 4. Baseline test counts (so you can detect regressions).
cd c:/01_Development/shipwright
uv run --extra dev pytest shared/tests/ 2>&1 | tail -3
# Expected: 2162 passed, 13 skipped, 18 deselected (as of 2026-05-21 session end)
uv run --extra dev pytest plugins/shipwright-compliance/tests/ 2>&1 | tail -3
# Expected: 434 passed
```

If any of these fail, STOP and ask the operator. Don't proceed with
broken baseline.

---

## Empirical verification — per iterate, per repo

For each iterate below: run the listed commands in BOTH repos, capture
the actual output, note what's visible vs invisible, and record
findings in the verification report (see "Reporting" section below).

### V-1. B.2 — SBOM undeclared-license triage

**Expectation:** `update_compliance.py --phase iterate` emits one
`source="sbom"` triage item per workspace with packages whose
licenses can't be resolved. Visible in `.shipwright/triage.jsonl`
and rendered in `.shipwright/agent_docs/triage_inbox.md` with a
copy-pasteable `cd <workspace> && npm install/uv sync && regen`
launchPayload.

**For each repo (shipwright + webui):**

```bash
cd <repo>

# 1. Snapshot pre-state.
cp .shipwright/triage.jsonl /tmp/triage-pre-b2-<repo>.jsonl 2>/dev/null || true
ls -la .shipwright/compliance/sbom.md

# 2. Run the SBOM emit path.
uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py \
    --project-root . --phase iterate 2>&1 | tee /tmp/update-compliance-<repo>.json

# 3. Verify telemetry in JSON output.
grep -A4 "sbom_triage" /tmp/update-compliance-<repo>.json

# 4. Verify per-workspace items landed.
grep "\"source\":\"sbom\"" .shipwright/triage.jsonl | head -5

# 5. Verify aggregator renders launchPayload.
grep -A8 "Launch payload" .shipwright/agent_docs/triage_inbox.md | head -20
```

**Visible-effect criteria:**
- [ ] `sbom_triage` key in JSON output contains `{appended: N, dismissed: N}` (no `error` key).
- [ ] At least one `source="sbom"` line in `triage.jsonl` for each repo with undeclared licenses (shipwright has Python deps from `pyproject.toml`; webui has client/ + server/ workspaces).
- [ ] `triage_inbox.md` shows a `cd <workspace> && ...` launchPayload block under at least one SBOM card.
- [ ] Re-running step 2 a second time: `sbom_triage.appended` is 0 (idempotency).

**Auto-resolve check (skip if too disruptive):**
- Pick the smallest workspace, run the actual `uv sync` / `npm install`.
- Re-run step 2.
- Confirm `sbom_triage.dismissed` increments for that workspace AND
  the matching card's `status` flipped to `dismissed` in `triage.jsonl`.

---

### V-2. B.3 — test-evidence Layer column + per-layer FAIL triage

**Expectation:** `update_compliance.py --phase iterate` regenerates
`test-evidence.md` with a new `Layer` column on `## Test Progression`
and new `Integration`/`pgTAP` columns on `## Full Suite Runs`. If the
latest `test_run` event has any failing layer, one
`source="test-evidence"` triage item per failing layer with
`eventId=<test_run event id>` cross-link.

**For each repo:**

```bash
cd <repo>

# 1. Inspect current test-evidence.md structure.
grep -A2 "## Test Progression" .shipwright/compliance/test-evidence.md | head -5
grep -A2 "## Full Suite Runs" .shipwright/compliance/test-evidence.md | head -5

# 2. Run the test-evidence emit path (already done in V-1's step 2, so just check output).
grep -A4 "test_evidence_triage" /tmp/update-compliance-<repo>.json

# 3. Find any test-evidence triage items.
grep "\"source\":\"test-evidence\"" .shipwright/triage.jsonl | head -5

# 4. Check eventId is set (B0 cross-link dogfood).
grep "\"source\":\"test-evidence\"" .shipwright/triage.jsonl | head -1 | python -c "import json, sys; d=json.loads(sys.stdin.read()); print('eventId:', d.get('eventId'))"
```

**Visible-effect criteria:**
- [ ] `## Test Progression` table header has 8 columns: `# | Event | Source | Layer | New Tests | Suite Total | Result | Date`.
- [ ] `## Full Suite Runs` table has 8 columns: `Run | Trigger | Unit | Integration | pgTAP | E2E | Smoke | Date`.
- [ ] At least one row in Test Progression shows a non-`—` Layer value (`unit | e2e | mixed`).
- [ ] If the repo has any failing test layer in the latest test_run: a `test-evidence:<layer>` triage item exists with `eventId` populated.

**If no test-evidence triage card appears:** check whether ANY
`test_run` event in `shipwright_events.jsonl` has a failing layer.
If they're all green, that's the expected "no work for operator"
state — note it in the report, don't manufacture a failure.

---

### V-3. B.4 — RTM `FAIL → trg-XXX` deep-link (KNOWN GAP — verify the workaround)

**This is the iterate the previous session ducked.** The B.4 code
reads `frId` from triage items and renders deep-links in the
Requirements Coverage Status cell. But **no producer in the campaign
populates `frId`** — B.2 SBOM is per-workspace, B.3 test-evidence is
per-layer. The feature is dead-on-arrival on real repos without an
FR-aware producer.

**Two-step verification:**

**Step A — Confirm the gap is real:**

```bash
cd c:/01_Development/shipwright
grep -c "\"frId\":\"FR-" .shipwright/triage.jsonl   # expect 0
grep "FAIL → \[trg-" .shipwright/compliance/traceability-matrix.md   # expect no matches
```

```bash
cd c:/01_Development/shipwright-webui
grep -c "\"frId\":\"FR-" .shipwright/triage.jsonl   # expect 0
grep "FAIL → \[trg-" .shipwright/compliance/traceability-matrix.md   # expect no matches
```

If both `grep -c` show 0 and no FAIL deep-links exist, the gap is
confirmed. The user is right that the feature has zero visible
effect.

**Step B — Synthetic verification that the code path actually works:**

Manually append one triage item with `frId` set to a real FR ID in
each repo, regenerate the RTM, and verify the deep-link renders.

```bash
cd c:/01_Development/shipwright

# Pick the first FR from the RTM (e.g. FR-01.01).
real_fr=$(grep -oE "FR-[0-9]+\.[0-9]+" .shipwright/compliance/traceability-matrix.md | head -1)
echo "Using FR: $real_fr"

# Append a synthetic triage item.
uv run python -c "
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('shared/scripts')))
import triage
new_id = triage.append_triage_item(
    '.',
    source='test-evidence', severity='high', kind='bug',
    title=f'SYNTHETIC verification card for $real_fr',
    detail='Manual seed to verify B.4 deep-link rendering.',
    fr_id='$real_fr',
)
print('seeded:', new_id)
"

# Regenerate the RTM.
uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py \
    --project-root . --phase iterate 2>&1 | tail -5

# Verify the deep-link IS rendered now.
grep "FAIL → \[trg-" .shipwright/compliance/traceability-matrix.md
grep "$real_fr" .shipwright/compliance/traceability-matrix.md | grep "FAIL → "
```

Repeat for webui with a webui-specific FR.

**Visible-effect criteria:**
- [ ] After seeding the synthetic frId-bearing card: `grep "FAIL → \[trg-"` returns at least one match in the matching FR row.
- [ ] The Coverage Summary's `### FRs with open triage items` subsection now lists the FR with the deep-link.
- [ ] `### FRs without tests` / `### FRs with stale verification (> 14 days)` subsections render if applicable (webui's RTM has multiple stale FAIL rows historically — likely to fire).

**After verification, CLEAN UP THE SYNTHETIC CARDS** to avoid
polluting the real triage:

```bash
# Dismiss the synthetic cards you created.
uv run python -c "
import sys, pathlib
sys.path.insert(0, str(pathlib.Path('shared/scripts')))
import triage
for item in triage.read_all_items('.'):
    if 'SYNTHETIC verification' in item.get('title', ''):
        triage.mark_status('.', item['id'], new_status='dismissed',
                            by='verification', reason='synthetic-test-cleanup')
        print('dismissed:', item['id'])
"

# Regenerate so the synthetic cards drop from the inbox render.
uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py \
    --project-root . --phase iterate 2>&1 | tail -3
```

**Decision for the operator (write this in the report):**

Should the campaign ship a follow-up iterate that adds an FR-aware
triage producer (so the B.4 feature has visible real-world output)?
Options:

1. **Phase-quality FR mapper:** when a phase-quality check fires
   that's traceable to an FR via spec section path, set `frId` on
   the resulting triage card.
2. **Test-suite → FR map:** extend `shipwright_test_results.json` (or
   a separate map file) so the B.3 test-evidence producer can resolve
   failing-test-suite → owning-FR.
3. **Manual `--fr-id` flag** on `record_event.py` task_created /
   ad-hoc triage producers so operators can stamp FRs onto cards
   when they have context.

Recommend option (3) for the smallest patch — biggest unlock for the
quietest cost.

---

### V-4. C.1 — FR-or-change-type gate

**Expectation:** Every `record_event.py --type work_completed --source iterate`
call MUST carry either `--affected-frs FR-...` OR `--change-type
<docs|tooling|compliance|infra> --none-reason "..."`. Reject otherwise
(exit 1, no event written). Applies to ALL iterates including BUG.

**For each repo:**

```bash
cd <repo>

# 1. Try to record an unclassified iterate event — should reject.
uv run shared/scripts/tools/record_event.py \
    --project-root . --type work_completed --source iterate \
    --intent feature \
    --commit "$(git rev-parse HEAD)" \
    --description "VERIFICATION: unclassified — should reject"
# Expect: exit 1, `fr_gate_unclassified` in stderr, NO new event in shipwright_events.jsonl.
echo "exit: $?"

# 2. Try with --affected-frs — should pass.
real_fr=$(grep -oE "FR-[0-9]+\.[0-9]+" .shipwright/planning/*/spec.md 2>/dev/null | head -1 | cut -d: -f2)
[ -z "$real_fr" ] && real_fr="FR-01.01"  # webui fallback
uv run shared/scripts/tools/record_event.py \
    --project-root . --type work_completed --source iterate \
    --intent feature --spec-impact none --spec-impact-justification "verification test" \
    --commit "$(git rev-parse HEAD)" \
    --description "VERIFICATION: with affected-frs — should pass" \
    --affected-frs "$real_fr"
echo "exit: $?"

# 3. Try with --change-type + --none-reason — should pass.
uv run shared/scripts/tools/record_event.py \
    --project-root . --type work_completed --source iterate \
    --intent bug \
    --commit "$(git rev-parse HEAD)" \
    --description "VERIFICATION: bug+change-type — should pass" \
    --change-type tooling --none-reason "verification test"
echo "exit: $?"

# 4. Try with --change-type but no --none-reason — should reject.
uv run shared/scripts/tools/record_event.py \
    --project-root . --type work_completed --source iterate \
    --intent bug \
    --commit "$(git rev-parse HEAD)" \
    --description "VERIFICATION: change-type without reason — should reject" \
    --change-type tooling
echo "exit: $?"

# 5. Try with multi-line --none-reason — should reject (C.1 stricter validation).
uv run shared/scripts/tools/record_event.py \
    --project-root . --type work_completed --source iterate \
    --intent bug \
    --commit "$(git rev-parse HEAD)" \
    --description "VERIFICATION: multi-line reason — should reject" \
    --change-type tooling --none-reason "first line
second line"
echo "exit: $?"
```

**Visible-effect criteria:**
- [ ] Step 1: exit 1, JSON output has `"error": "fr_gate_unclassified"`.
- [ ] Step 2: exit 0, event appears in `shipwright_events.jsonl`.
- [ ] Step 3: exit 0, event appears with `"change_type":"tooling"` + `"none_reason":"verification test"`.
- [ ] Step 4: exit 1.
- [ ] Step 5: exit 1.

**Cleanup the verification events:**

```bash
# Use record_event's event_amended to mark these as test/superseded,
# or grep them out manually. Don't leave them polluting the audit trail.
# Easiest: keep them; they're labeled "VERIFICATION:" so they're
# self-documenting. Note in the report that 3 verification events
# were left in the log (or remove them by editing the file directly).
```

---

### V-5. C.2 — F4-F7 audit detectors

**Expectation:** `audit_detector.run_all()` (which runs when the
operator invokes `/shipwright-compliance` or the audit phase) emits
4 new detective-only findings under Group F:

- F4 ADR-bloat
- F5 Architecture-drift
- F6 CLAUDE.md > 200 lines
- F7 CLAUDE.md inline iterate-annotation > 5

**Run the audit on each repo:**

```bash
cd <repo>

# The audit detector entrypoint.
uv run plugins/shipwright-compliance/scripts/audit/run_audit.py \
    --project-root . --format json 2>&1 | tee /tmp/audit-<repo>.json

# Pull out the F4-F7 findings specifically.
python -c "
import json
with open('/tmp/audit-<repo>.json') as f:
    data = json.load(f)
for finding in data.get('findings', []):
    if finding.get('check_id') in ('F4','F5','F6','F7'):
        print(finding['check_id'], finding['status'], finding.get('severity', ''), '-', finding.get('name', '')[:60])
        print('  detail:', finding.get('detail', '')[:200])
"
```

**Visible-effect criteria per repo:**

- **shipwright:**
  - [ ] F4: probably `pass` (decision_log.md ADRs are mostly small — but inspect any > 60-line ADR without `**Details:**` link).
  - [ ] F5: depends — if no `architecture_impact ∈ {component, data-flow}` drops exist beyond the marker, `pass`. Otherwise drift.
  - [ ] F6: `pass` (CLAUDE.md is 133 lines, well under 200).
  - [ ] F7: depends on count of "Iterate X.Y" mentions in CLAUDE.md.

- **webui:**
  - [ ] F4: likely `fail` if any ADRs in decision_log.md haven't been refactored to spec files yet.
  - [ ] F5: likely `pass` (depends on drops state).
  - [ ] **F6: should `fail` — webui's CLAUDE.md is ~270 lines.** This is the canonical test of the F6 detector.
  - [ ] F7: likely `fail` if iterate annotations leak into CLAUDE.md.

**If F6 doesn't fire on webui's 270-line CLAUDE.md, the detector is
broken.** Investigate before reporting success.

---

### V-6. C.3 — plugin-cache vs repo drift detector

**Expectation:** `scripts/check_plugin_cache_sync.py` walks
`<repo>/plugins/shipwright-*` and compares each against the
lexically-newest SemVer cache version under
`~/.claude/plugins/cache/shipwright/<plugin>/<version>/`.

**Only the monorepo carries `plugins/`, so this only runs
meaningfully on shipwright. Webui has no `plugins/` dir → script
should skip cleanly.**

```bash
# 1. Run on the monorepo.
cd c:/01_Development/shipwright
uv run scripts/check_plugin_cache_sync.py 2>&1 | tee /tmp/cache-sync-shipwright.txt
uv run scripts/check_plugin_cache_sync.py --json 2>&1 | tee /tmp/cache-sync-shipwright.json

# 2. Verify behavior on a repo without plugins/.
cd c:/01_Development/shipwright-webui
uv run --project c:/01_Development/shipwright \
    c:/01_Development/shipwright/scripts/check_plugin_cache_sync.py \
    --repo-root . 2>&1 | tee /tmp/cache-sync-webui.txt
```

**Visible-effect criteria:**

- **shipwright (with plugins/):**
  - [ ] Script exits 0 (default fail-soft).
  - [ ] Output is either `plugin-cache-sync: ok ...` OR
    `plugin-cache-sync: WARN — N plugin(s) drifted` followed by
    per-plugin details on stderr.
  - [ ] `--json` output is valid JSON with `status`, `plugins`,
    `drifted_count`.
  - [ ] If drift is reported: the operator runs
    `bash scripts/update-marketplace.sh` and re-runs the script;
    drifted count drops.

- **webui (no plugins/):**
  - [ ] Script exits 0 with `plugin-cache-sync: skip — no plugins/ dir in repo`.
  - [ ] No false-WARN on stderr.

---

## Reporting

Create a verification report at
`c:/01_Development/shipwright/.shipwright/planning/campaigns/2026-05-21-artifact-polish-empirical-results.md`
with this structure:

```markdown
# Empirical Verification Results — Artifact-Polish Campaign

**Verified:** 2026-05-21 (or whenever you run this)
**Verifier:** Claude Code session (this one)
**Repos tested:** shipwright (monorepo), shipwright-webui (adopted)

## Setup checklist
- [ ] Marketplace sync run + verified.
- [ ] Baseline test counts confirmed.

## Per-iterate results

### B.2 SBOM
- shipwright: <visible-effect criteria → pass/fail per checkbox>
- webui: <same>
- Open issues: <any>

### B.3 test-evidence
- ... (same shape)

### B.4 RTM deep-link
- Gap confirmed: <yes/no>
- Synthetic verification: <pass/fail>
- Recommended follow-up: <option 1/2/3 from V-3>

### C.1 FR-gate
- ... (same shape)
- Verification events left in log: <yes/no, count>

### C.2 audit detectors
- shipwright: <F4/F5/F6/F7 statuses>
- webui: <F4/F5/F6/F7 statuses — F6 MUST fire if CLAUDE.md > 200>

### C.3 cache-sync
- shipwright drift state: <ok | drift | not_in_cache + counts>
- webui skip behavior: <verified clean | WARN false-positive>

## Cleanup actions taken
- Synthetic triage cards dismissed: <count>
- Verification events removed: <yes/no>

## Bugs / gaps to fix
1. <list each issue with file:line + suggested fix>

## Recommended follow-ups
1. FR-aware triage producer to give B.4 visible output (see V-3 options).
2. <other items>

## Sign-off
- [ ] Operator-reviewed
- [ ] Decision on B.4 follow-up: <option N>
```

## Ping the operator (don't auto-proceed) when:

1. **Baseline test counts don't match** (2162 shared / 434
   compliance). A regression masks empirical drift.
2. **F6 doesn't fire on webui's CLAUDE.md** — that's the canonical
   real-world test of the detector. Either the detector is broken
   or webui's CLAUDE.md has been trimmed since.
3. **C.1 gate doesn't reject step 1** — would mean the gate isn't
   actually in effect; investigate which CLI version is running.
4. **`uv sync` / `npm install` would touch GB of disk** in B.2's
   auto-resolve check — skip the auto-resolve verification, note
   in report.
5. **Any commit you'd otherwise make** — verification should NOT
   merge code. If you find a bug, write it up in the report; don't
   silently fix-and-ship.

## Risk register

- **Triage pollution.** B.4 synthetic cards must be dismissed at the
  end of V-3. C.1 verification events stay in the log but are
  self-labeled "VERIFICATION:".
- **Webui modifications.** Don't run `update_compliance.py` or
  `update-marketplace.sh` against webui as cleanup steps without
  operator approval — webui carries its own gitignored state.
- **Cache-sync false drift.** If C.3 reports drift in the live
  monorepo, that's expected — fixture files under
  `plugins/*/tests/fixtures/` legitimately don't sync. Note the
  count and which plugin; don't reflexively re-sync.

## Optional: start-here checklist

```text
[ ] git -C c:/01_Development/shipwright pull --ff-only origin main
[ ] git -C c:/01_Development/shipwright log --oneline -8  # confirm d27a889 HEAD
[ ] bash c:/01_Development/shipwright/scripts/update-marketplace.sh
[ ] uv run --extra dev pytest shared/tests/ 2>&1 | tail -3   # 2162 baseline
[ ] Read this handover top to bottom
[ ] Start V-1 (B.2) on shipwright, then webui
[ ] ...through V-6
[ ] Write empirical-results.md
[ ] Stop. Don't merge. Report to operator.
```

Good luck. The previous session was confident based on tests; the
operator wants confidence based on real-repo output. Don't make the
same mistake.
