# Step 5-int-arch — Internal Architecture Review (always, right after 5-int)

**Runs exactly once, before Branch A/B/C, regardless of `external_review_status`.**
A separate fresh-context pass from Step 5-int, not an extension of
`opus-plan-reviewer` — escaping the plan's own reasoning frame, same reason
Step 5a's *external* architecture review is a second call, not a reuse of the
plan-review call. **Does not carry the Pre-5b gate** — only Step 5-int
(`Ran: yes`) or a completed Branch A external review count as "independently
reviewed" there. If `## Internal Architecture Review` already exists in
`plan.md` **and records `Ran: yes`**, skip straight to branching — do not
re-spawn; a recorded `Ran: no` is not a completed pass — retry it,
overwriting the existing section in place.

**Write the brief first.** Author `{planning_dir}/architecture_brief.md` from
`shared/templates/architecture_brief.md` NOW — this pass runs before Step 5a,
which used to author the brief and now re-reads/refreshes this same file
instead. List the options **without** the reasons any were rejected; never
copy the plan's rejected-alternatives rationale into it.

**Reuse the tier Step 5-int already resolved** — SAME `plan_review` role, this
pass is not a fifth role, so there is no second `resolve_model_tier.py` call
here. Spawn `shipwright-plan:architecture-internal-reviewer` (Read/Grep/Glob only)
over the architecture brief + `{spec_file}` — **never `plan.md`**, the same
anchoring defense the brief already gives Step 5a. Pass that same
`agent_param` as the Agent tool's `model=` parameter when non-null; omit when
`null`.

**No Codex transport yet.** Under `--driver codex` (or `CODEXTENDER_ACTIVE`
set), do NOT spawn — reusing `role="plan_review"`'s Codex leg would collide on
the canonical basename Step 5-int's Internal Plan Review already writes. Record
`Ran: no (no Codex transport for architecture_internal yet)` and continue — a
full Codex-side role is an explicit follow-up, out of scope here.

**Degraded handling** mirrors Step 5-int: unreachable subagent, unparseable
reply, or missing `findings`/`summary` → record `Ran: no` (reason) in the
`## Internal Architecture Review` section and `decision_log.md`, then
**continue to branching as normal**.

**Triage every finding** — fix (integrate into `plan.md` now), disclose
(known limitation, below), or decline (reason; same scope-ratchet guard as
Step 5-int). A declined/disclosed `severity: high` finding **STOPs and asks
the user** before Step 6, same shape as Step 5-int/5a. Under `single_session`,
`plan.architecture-internal-review-high-severity-declined` carries the
auto-default — its own gate id, not Step 5-int's.

**Write, always** (never a second heading, no marker of its own — provenance
is `plan.md` + `decision_log.md`):

```markdown
## Internal Architecture Review (architecture-internal-reviewer)
- **Ran:** {yes | no (capability failure) | no (parse failure) | no (no Codex transport for architecture_internal yet)}
- **Severity:** {low|medium|high, or n/a if Ran: no}
- **Summary:** {reviewer's one-line assessment, or the failure reason if Ran: no}
- **Findings:** {one line per finding: category, severity, disposition, reason}
- **Known limitations:** {each disclosed finding, one line, or `none`}
- **Status:** {clean | N fixed | N fixed, M disclosed, K declined | not_run}
```

**Log every finding** to `decision_log.md`, `--section "Internal Architecture
Review — {split_name}"`, same `--decision`/`--rejected` shape as Step 5-int.
Then branch on `external_review_status`, per [step-5-external-review.md](step-5-external-review.md).
