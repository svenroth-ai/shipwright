# opus-plan-reviewer internal plan review — iterate-2026-09-20-r0-resolve-1a-envelope-delivery

Reviewed the iterate spec's first-draft `## Decision` (file-based envelope
design) + mini-plan, via SKILL.md Step "Internal Plan Review". Severity: high.

## Findings

1. **completeness/high — AC drift, unfired blocking clause.** The sub-iterate's
   own AC5 requires trust confirmed "via `codex /hooks`"; the run spec's own
   copy dropped that clause and checked the box. Trust was never confirmed —
   only bypassed. AC6 (blocking-finding-for-R2 on unconfirmed trust) should
   have fired and did not. Since M9 is excluded from this slice, "the
   enforcement mechanism may be installed and silently inert" is the single
   largest residual risk and was unnamed.
2. **architecture/high — the decision silently redefines "envelope" in a way
   that collides with the parent spec.** M7 specifies a prompt-borne closed
   grammar delivered by the adapter or a documented helper; M3 says
   `UserPromptSubmit` mints the token and helpers "look up only the exact
   token, never 'latest by cwd/session'." The draft's cwd-keyed on-disk file,
   read directly by `PreToolUse`, is exactly the "latest by cwd" lookup M3
   forbids. Fix: state explicitly that the chain is file → `UserPromptSubmit`
   recognizes/validates → mints a session/turn-scoped token →
   `PreToolUse` matches the exact token (M3/M7-compatible) — not a direct
   file read from `PreToolUse`.
3. **completeness/high — "Named gap" understated.** Missing: arming is
   opt-in (a forgotten mint is indistinguishable from today's unenforced
   behavior, given M3's own documented fail-open on missing/stale records);
   the hook-trust inertness; the subagent tool-name mismatch's consequence
   for the matcher inventory; probe 5's (now probe 6's) `--ephemeral`
   limitation.
4. **architecture/high — runtime-neutral expansion conflicts with the
   campaign's own acceptance bar.** Campaign §4 AC5 / R2's own AC3 require
   Claude-driven iterates unaffected; R2's own scope line says "Register ...
   for Codex" only. Registering a new Claude-side `PreToolUse` denial by
   default would also ship to every consumer project via `plugins/*/hooks/
   hooks.json`, unannounced.
5. **completeness/high — cross-runtime answer's two reasons are internally
   inconsistent.** Reason 1 (Claude never loads Codex's hooks.json) stops
   being true the moment the same logic is registered from Claude's own
   hooks.json, as the decision itself proposed. Reason 2 (session/turn
   scoping) is a property of the *in-session* activation record, not the
   pre-session artifact the draft claimed carried it.
6. **completeness/high — AC4 not met; `Affected Boundaries: n/a` wrong in
   spirit.** The decision's entire content is a new on-disk format two
   runtimes/three surfaces/two repos will read and write. Undecided:
   file path/location, schema/version, scoping keys, lookup rule, expiry,
   atomic one-time-consume semantics, session-mismatch behavior, Windows cwd
   normalization, per-tool-class matcher inventory.
7. **security/medium — the activation grant is a file on disk with no stated
   protections.** No gitignore/ACL/one-time-nonce/reap-on-stale semantics
   recorded; this repo has a documented footgun where `git add -A` sweeps
   derived snapshots into commits. M7's own analogous webui mechanism uses a
   server-side one-time nonce, restrictive ACLs, deletion after handoff, and
   reaping — precautions the draft dropped without saying why.
8. **completeness/medium — "0 untested-testable" inaccurate.** Two
   load-bearing, cheaply testable claims were never probed: PreToolUse deny
   against the aliased `collaborationspawn_agent` name specifically (only
   Bash-class deny was proven); and whether `UserPromptSubmit` can mint a
   token from real `session_id`/`turn_id`/`cwd` and deliver it via
   `additionalContext` at all.
9. **completeness/medium — ledger rows 7-8 mislabeled.** `covered-by-existing-test`
   requires a *named pre-existing test* per the closed vocabulary
   (`confidence-anti-patterns.md`); the rows cited architectural reasoning,
   not a test.
10. **completeness/medium — evidence provenance inconsistent.** Prose claimed
    "5 live runs" while the ledger cited `run6`; probe numbering in prose
    didn't match probe numbering in the ledger; all raw artifacts lived only
    under a session-scoped scratchpad that won't exist for a future reader.
11. **architecture/medium — Desktop-app coverage rests on an unflagged second
    premise.** Whether OpenAI's Desktop app loads project-level
    `.codex/hooks.json` and applies the same trust model at all was never
    checked — only "is the envelope file findable from that cwd" was
    flagged as open.
12. **completeness/low — dangling cross-references** (mini-plan "see Decision
    §4", ledger "ADR Decision §3" — neither existed in the draft as written);
    and the ADR closing Phase 0.5 could be misread as also closing the parent
    spec's Phase 0 spend decision, which it does not.

## Disposition

All twelve findings accepted; none declined or disclosed-only. Findings 1, 8
drove the explicit blocking-finding-for-R2 on hook trust. Finding 2 (with
live probe 7, added post-review) drove the `UserPromptSubmit`-mint redesign.
Finding 4/5 drove scoping Claude-side registration out of R2 as a separate,
later decision. Findings 6, 7 drove the new "Contract for R2" section.
Findings 3, 9, 10, 11, 12 drove direct edits to "Named gap", the Test
Completeness Ledger, probe numbering, and the Desktop-app framing in the
revised spec.
