# B5 — PreToolUse cross-phase firing (measurement-gated)

- **Type:** investigation → maybe change
- **Complexity:** small (spike first; change only if justified)
- **Depends on:** B0
- **Priority:** LOWEST — do NOT bundle with the duplicate-fan-out cases.

## Why PreToolUse is a different problem

PreToolUse hooks are **plugin-local** — each registered in exactly ONE
plugin, so there is **no** "N redundant copies" duplication:

| Hook | Plugin | Matcher |
|---|---|---|
| `validate_command.sh` | build | Bash |
| `check_rtm_coverage.py` | compliance | Bash |
| `check_security_scan.py` | compliance | Bash |

The Stop/SessionStart consolidation does **not** apply — there is nothing
to de-duplicate. The *real* issue is the same no-active-plugin-filter:
these 3 hooks **fire on every Bash call in every session regardless of
phase**, so compliance's RTM-coverage and security-scan gates run during
unrelated build/iterate work. That is **cross-phase contamination**, not
duplication — and it sits on the **hot path** (before every tool call).

## Approach

1. **Measure first (the spike).** Quantify the actual cost: do
   `check_rtm_coverage.py` / `check_security_scan.py` do real work (IO,
   subprocess) when fired outside a compliance session, or are they
   already cheap fail-open no-ops? Capture added latency per Bash call.
2. **Only if material:** phase-scope them behind `resolve_engaged_phase`
   (B0) — but weigh the resolver call's own hot-path latency. A cheap
   early-exit guard (env/marker check) may beat a full resolve.
3. **If immaterial:** document the finding and **leave as-is**. Closing
   this with "measured, not worth it" is a valid outcome.

## Acceptance Criteria

- [ ] **AC-1.** A measurement note: per-Bash-call overhead of the 3
      PreToolUse hooks in a non-compliance session.
- [ ] **AC-2.** A decision: phase-scope vs. leave-as-is, with the latency
      tradeoff recorded.
- [ ] **AC-3 (if change).** Hooks fast-exit when their phase is not
      engaged, without a measurable hot-path regression.

## Out of scope

- Any change purely "for symmetry" with B1–B4. PreToolUse earns a change
  only if measurement justifies it.
