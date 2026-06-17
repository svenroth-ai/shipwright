# Handover — Artifact-Polish Campaign Completion (B.2 → C.3)

> **For a fresh Claude Code session.** Read this from disk at
> `c:/01_Development/shipwright/.shipwright/planning/campaigns/2026-05-21-artifact-polish-completion-handover.md`
> or have the operator paste the contents into the prompt. The
> campaign-state-file at
> `.shipwright/planning/campaigns/2026-05-21-artifact-polish-completion-state.md`
> is your running log — update it after each iterate so a future
> session can pick up if yours dies.

---

## Context: where the campaign sits

The artifact-polish plan
(`~/.claude/plans/ich-habe-ein-paar-imperative-emerson.md`) is mid-flight.
**Completed** on `main`:

| Iterate | PR  | Squash commit | What landed                                                    |
|---------|-----|---------------|----------------------------------------------------------------|
| A.1     | #48 | `3244807`     | Mermaid architecture marker (`shipwright:architecture v=2`)    |
| A.3     | #49 | `9addb9a`     | ADR hard-reject + `spec_ref` + `.shipwright/planning/adr/INDEX.md` |
| A.4     | #50 | `822f5fa`     | 4-stage session-id fallback chain                              |
| (fix)   | #51 | `823225e`     | section-builder.md JSON examples conform to schema             |
| B0      | #52 | `f2aaf89`     | Triage producer contract — schema + RTM-link fields + render polish |
| B.1     | #53 | `c24dd6e`     | Compliance dashboard mode-aware + Why-warn column + Triage open |
| (fix)   | #54 | `f4a1ff1`     | gh-security action-unit emit gate symmetry                     |
| (chore) | #55 | `5c06748`     | Canon-lint allowlist for `.shipwright/planning/adr/**.md`      |

**Pre-existing failures eliminated.** As of `5c06748` the full
`shared/tests/` suite is 2101/2101 green. **No tolerated baseline
failures.** If a new fail appears, treat it as in-scope unless
demonstrably unrelated.

**Remaining iterates (this campaign):**

| Order | Iterate | Predicted ADR | Predicted branch                                    | Scope                                                                   |
|-------|---------|---------------|-----------------------------------------------------|-------------------------------------------------------------------------|
| 1     | B.2     | ADR-056       | `iterate/b2-sbom-polish`                            | Triage 1-per-workspace for SBOM `undeclared` (ADR-054 D1)               |
| 2     | B.3     | ADR-057       | `iterate/b3-test-evidence-layer-and-triage`         | Layer column + 1-per-layer FAIL triage (ADR-054 D2/D3) + `eventId` schema fix |
| 3     | B.4     | ADR-058       | `iterate/b4-rtm-deep-link-and-coverage`             | `FAIL → [trg-XXX](triage_inbox.md#trg-XXX)` deep-link render + Coverage Summary rewrite |
| 4     | C.1     | ADR-059       | `iterate/c1-fr-gate-finalize`                       | Hard-enforce FR-or-change-type at iterate-finalize (forward-only)       |
| 5     | C.2     | ADR-060       | `iterate/c2-architecture-and-adr-drift-detector`    | Audit-detector: ADR-bloat, arch-drift (consumes A.1 marker), CLAUDE.md-bloat |
| 6     | C.3     | ADR-061       | `iterate/c3-plugin-cache-sync-check`                | Python script comparing `~/.claude/plugins/cache/shipwright/` vs repo HEAD |

C.4 from the plan is already covered by A.4.

---

## Audience principle — the single rule that beats every micro-decision

Solo dev today, leadwright autonomous Phase 3 tomorrow. **Wenig Lärm,
nur dort aufpoppen wo es relevant ist. Alles andere ist accepted.**

When two reasonable choices come up — pick the quieter one. The
launch-surface principle from B0 ADR-054 generalises: an inbox /
dashboard / RTM-row entry must be **one handling**, not one finding.

---

## Per-iterate workflow (canonical)

Every iterate in this campaign follows the same shape. Do NOT skip
steps — they exist because earlier iterates in this session learned
why each one matters.

### 1. Branch + pre-flight recon (5 min)

```bash
git -C c:/01_Development/shipwright checkout main
git -C c:/01_Development/shipwright pull --ff-only origin main
git -C c:/01_Development/shipwright checkout -b iterate/<slug-from-table>
```

Read the relevant section of `~/.claude/plans/ich-habe-ein-paar-imperative-emerson.md`.
Then read the existing implementation file(s) for the iterate's target.
**Verify the plan's empirical claims** — e.g. file paths, line numbers,
expected behavior. Two prior plan-corrections in this campaign:

- B0 found `scope` is NOT the adopt-vs-greenfield signal — `run_config.adoption` is.
- The plan undercounts what already shipped via parallel work (the
  triage-launch-surface campaign absorbed ~70% of "B0"). Check
  `git log --all --since=2026-05-01 -- <relevant file>` and the
  memory files before assuming the plan is current.

### 2. Implementation

Smallest possible diff that satisfies the iterate's acceptance criteria.
**Additive when possible** (new optional kwargs, new rows, new files),
breaking only when the plan explicitly justifies it (e.g. A.3
hard-reject).

For B.2 / B.3: consult ADR-054 D1/D2/D3 at
`.shipwright/planning/adr/054-triage-producer-contract.md` — the
granularity decisions are already made. Don't re-litigate.

For B.4: producer-side fields (`frId`, `suiteId`, `eventId`) already
exist on triage append events from B0. RTM-side rendering reads
`triage.read_all_items()`, filters by `frId == row.fr_id`, and emits
`[FAIL → trg-XXX](../agent_docs/triage_inbox.md#trg-XXX)`. Anchor IDs
on cards are already emitted by B0's `aggregate_triage.py`.

For C.1: Phase 0a finished cleanup (memory:
`project_triage_inbox_roadmap` and event-log records). No staged
rollout — hard-enforce immediately, as the plan instructs.

For C.2: ADR-bloat finding uses dedup-key `adr-bloat:<adr-number>`,
arch-drift uses `arch-drift:since:<commit>` (B0 producer contract).
CLAUDE.md-bloat detector: regex-count of `Iterate [0-9A-Z]+ \(?ADR-[0-9]+\)?`
in CLAUDE.md > 5 → triage finding (per plan C.2 spec).

For C.3: Python (not shell) per plan, ~50 LOC, `scripts/check_plugin_cache_sync.py`,
fail-soft WARN, no-op when `~/.claude/` missing (CI).

### 3. Tests — extend existing, no new files

CLAUDE.md global rule: extend existing test files. The repo has rich
test coverage; new test files are almost never the right call.
Concrete targets per iterate:

- B.2 → `plugins/shipwright-compliance/tests/test_sbom_generator.py` + `test_data_collector.py`
- B.3 → `plugins/shipwright-compliance/tests/test_test_evidence.py` + `shared/tests/test_record_event.py` (layers schema)
- B.4 → `plugins/shipwright-compliance/tests/test_rtm_generator.py`
- C.1 → `shared/tests/test_finalize_iterate.py` (+ FR-gate negative tests)
- C.2 → `plugins/shipwright-compliance/tests/test_audit_detector.py`
- C.3 → new file is OK here (no existing equivalent): `shared/tests/test_plugin_cache_sync.py`

**Negative tests are non-negotiable.** Every gate / hard-reject /
schema-validation MUST have a paired negative test.

### 4. Iterate spec + ADR spec

```
.shipwright/planning/iterate/2026-05-21-<slug>.md       # iterate spec
.shipwright/planning/adr/<NNN>-<slug>.md                # long-form design rationale
```

Pattern: see `054-triage-producer-contract.md` and
`055-compliance-dashboard-mode-aware.md` for templates. The ADR spec
gets a "What landed in <Iterate> vs forward-looking" table at the top.

### 5. F3 + F4 drops (exercises A.3's `spec_ref` dogfood)

```bash
uv run shared/scripts/tools/write_decision_drop.py \
  --project-root . \
  --run-id "iterate-2026-05-21-<slug>" \
  --section "Iterate <X.Y> — <title>" \
  --title "<short title>" \
  --context "<why — 1-3 sentences, <500 chars>" \
  --decision "<what — same budget>" \
  --consequences "<impact — same budget>" \
  --rationale "<reasoning — same budget>" \
  --rejected "<alternatives — same budget>" \
  --architecture-impact <component|data-flow|convention|none> \
  --spec-ref ".shipwright/planning/adr/<NNN>-<slug>.md"

uv run shared/scripts/tools/write_changelog_drop.py \
  --project-root . \
  --run-id "iterate-2026-05-21-<slug>" \
  --category <Added|Changed|Fixed|...> \
  --bullet "<short bullet>"
```

Hard-reject on overflow is real now (A.3) — shorten + use `spec_ref`.

### 6. Docs updates (CLAUDE.md mandatory)

Touch the relevant section(s) of:

- `docs/guide.md` (Chapter 4 phase descriptions, or appendix for ADRs / RTM / SBOM)
- `docs/hooks-and-pipeline.md` (Artifact Write Matrix; hooks registry; between-phase actions)

If a hook is added/removed/reordered, or a phase-validator changes,
update hooks-and-pipeline.md or the CLAUDE.md gate (run by hooks)
breaks. C.1 in particular touches this.

### 7. EXTERNAL LLM review — **mandatory**, not self-review

This is a hard requirement from the operator. The general-purpose
agent self-review used in B0 / B.1 is **insufficient** for this
campaign. Use the actual external-review machinery.

```bash
# 7a — gate check (always run first)
uv run shared/scripts/checks/check-external-review-keys.py
# JSON output: status ∈ {available, missing_keys, user_disabled}
```

**Branch A — `available`:** keys present, not disabled. Run the
external mini-plan / iterate-spec review:

```bash
uv run shared/scripts/tools/external_review.py \
  --mode iterate \
  --spec-file ".shipwright/planning/iterate/2026-05-21-<slug>.md" \
  --plan-file ".shipwright/planning/iterate/2026-05-21-<slug>.md" \
  --plugin-root "~/.claude/plugins/cache/shipwright/shipwright-plan/0.3.1"
```

(For these iterates the spec is small enough that `--spec-file` and
`--plan-file` can both point at the iterate spec — there is no separate
miniplan file. Verify by reading the prior iterate specs for shape.)

Parse `reviews.gemini.feedback` + `reviews.openai.feedback`. Address
high/medium findings BEFORE proceeding to commit. Each finding logged
in the ADR's `External-Review-Findings` table with disposition
(`accepted-and-fixed` / `rejected-with-reason`).

**Branch B — `missing_keys`:** STOP and ask the operator verbatim
(per `references/iteration-planning.md`). The operator MAY add a key
to `.env.local`, OR opt out — in which case log the opt-out reason in
the ADR and proceed without external review. Do NOT auto-fallback to
self-review without operator approval.

**Branch C — `user_disabled`:** config disabled; print notice, skip.

After Branch A / B / C, write the marker:

```bash
uv run shared/scripts/checks/mark-review-state.py \
  --planning-dir ".shipwright/planning/iterate" \
  --review-type iterate \
  --status <completed|skipped_user_opt_out|skipped_config_disabled> \
  --provider <openrouter|null> \
  --findings-count <N> \
  --reason "<optional>"
```

### 8. EXTERNAL CODE review — **mandatory after build, before commit**

Run after the implementation is done but BEFORE `git commit` so a
high-severity finding can still be addressed inline.

```bash
# Stage everything first so the diff captures all your changes
git -C c:/01_Development/shipwright add -A

# Capture the diff
git -C c:/01_Development/shipwright diff --cached > /tmp/shipwright-code-review-diff.txt

# Gate check (same as step 7a)
uv run shared/scripts/checks/check-external-review-keys.py
```

**Branch A — `available`:**

```bash
uv run shared/scripts/tools/external_review.py \
  --mode code \
  --diff-file /tmp/shipwright-code-review-diff.txt \
  --spec-file ".shipwright/planning/iterate/2026-05-21-<slug>.md" \
  --plugin-root "~/.claude/plugins/cache/shipwright/shipwright-plan/0.3.1"
```

Parse findings, address high/medium inline, log in the ADR's
`External-Code-Review-Findings` table.

If `skipped: "empty_diff"`: continue, mark `skipped_user_opt_out` with
reason `empty_diff` (per `iteration-reviews.md`).

**Branch B / C:** same opt-out flow as step 7.

Write the cascade marker:

```bash
uv run shared/scripts/checks/mark-review-state.py \
  --planning-dir ".shipwright/planning/iterate" \
  --review-type code \
  --status <completed|skipped_user_opt_out|skipped_config_disabled> \
  --provider <openrouter|null> \
  --findings-count <N> \
  --reason "<optional>"
```

### 9. Commit, push, PR, merge

```bash
git -C c:/01_Development/shipwright add <explicit-file-list>     # NEVER -A
git -C c:/01_Development/shipwright commit -m "$(cat <<'EOF'
<conventional-commit-subject>

<body — explain rationale, list external-review-finding dispositions, test counts>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
git -C c:/01_Development/shipwright push -u origin iterate/<slug>
```

PR title: `<conventional-commit-subject> (Iterate <X.Y>)`.

PR body: Summary / external-review findings (with dispositions) /
external-code-review findings / test plan / out of scope / doc updates.

Author identity check: `git config user.name` should be `svroch`,
email `218151234+svroch@users.noreply.github.com` (memory:
`feedback_git_identity`). Set with `git config user.name svroch` +
`git config user.email 218151234+svroch@users.noreply.github.com` if
the local config differs.

Then merge + pull local:

```bash
cd c:/01_Development/shipwright
gh pr merge <PR#> --squash --delete-branch
git checkout main
git stash push -- .shipwright/agent_docs/ .shipwright/compliance/ shipwright_events.jsonl  # if dirty
git pull --ff-only origin main
```

### 10. Update the campaign-state file

Write progress to
`.shipwright/planning/campaigns/2026-05-21-artifact-polish-completion-state.md`.
This is the safety net for context-loss recovery. Include for each
completed iterate:

- PR number + squash commit
- Test counts (`shared/tests/` + relevant plugin suite)
- External-review findings count + disposition summary
- External-code-review findings count + disposition summary
- Any deviations from this handover (and why)

### 11. ONLY at the end (after all 6 iterates merged): marketplace sync

```bash
bash c:/01_Development/shipwright/scripts/update-marketplace.sh
```

Do NOT run this between iterates. Tests run from the monorepo
directly, not from the cache. One final sync is enough.

---

## Ping the operator (do NOT proceed autonomously) when:

1. **External review finds a CRITICAL or HIGH** that isn't a quick
   inline fix — architectural decision needed.
2. **Plan scope materially diverges** — like B0 where 70% had already
   shipped via parallel work. Re-scope first.
3. **Real UX ambiguity** — like the 5 granularity questions before B0.
   Use `AskUserQuestion` to present concrete options.
4. **Branch B (`missing_keys`)** — operator decides between adding a
   key or opting out.
5. **Pre-existing failure appears** that genuinely is not in-scope —
   verify against `main` (`git stash && git checkout main && pytest && git checkout - && git stash pop`).
6. **A test or implementation choice would break A.3's spec-folder
   convention or B0's triage producer contract** — those are now
   load-bearing for downstream iterates.

---

## Risk register

- **Context-window / auto-compaction.** This is 6 iterates in one
  session. The campaign-state file is the recovery point. If
  compaction has hit and you suspect file-content drift, re-read
  before editing. Don't trust memory of file contents in a long
  session — CLAUDE.md "File Read Strategy" rule applies.

- **ADR-NNN prediction drift.** The predicted NNNs (056-061) assume
  no parallel ADR drops land between session start and the eventual
  `/shipwright-changelog` release. Single-user repo — low risk, but
  if you see existing drops in `.shipwright/agent_docs/decision-drops/`
  for OTHER runs, adjust your prediction. The spec-folder filename
  is just a convention; the link still resolves either way.

- **`docs/guide.md` and `docs/hooks-and-pipeline.md` merge conflicts.**
  Every iterate touches at least one of these. Sequential merges are
  safe; parallel ones would conflict. Stick to sequential.

- **External-review API availability.** Branch B (`missing_keys`) is
  realistic — keys can be missing or rate-limited. Treat each Branch B
  as a hard stop + operator decision.

---

## Final summary expected from the new session

After all 6 iterates merged + marketplace synced, post a single
message containing:

- PR list with squash commits
- Final `shared/tests/` + per-plugin test counts (compare to baseline
  2101 shared + 351 compliance + 237 iterate)
- External-review findings total per iterate + disposition counts
- External-code-review findings total per iterate + disposition counts
- Anything left in the campaign-state file's "deviations" section
- Marketplace-sync confirmation (cache hits on key new symbols per
  iterate, as B0 / B.1 reports did)

---

## Optional: start-here checklist for the new session

```text
[ ] git -C c:/01_Development/shipwright pull --ff-only origin main
[ ] git -C c:/01_Development/shipwright log --oneline -3   # confirm 5c06748 HEAD
[ ] uv run --extra dev pytest shared/tests/ 2>&1 | tail -3  # confirm 2101 baseline
[ ] cat .shipwright/planning/campaigns/2026-05-21-artifact-polish-completion-handover.md
[ ] cat .shipwright/planning/adr/054-triage-producer-contract.md   # B0 D1-D8 decisions
[ ] cat .shipwright/planning/adr/055-compliance-dashboard-mode-aware.md   # B.1 patterns
[ ] Start B.2: iterate/b2-sbom-polish
```

Good luck.
