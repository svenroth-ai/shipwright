# Iterate Spec — P4.1 Skill Bootstrap Pack (SP2 + SP4)

- **run_id:** `iterate-2026-05-29-skill-bootstrap-pack`
- **Type:** FEATURE · **Complexity:** medium (classifier floor=small; raised for
  cross-cutting hook wave ×12 + `touches_io_boundary` + 2 runtime-prompts + meta-test)
- **Spec source:** `Spec/external-frameworks-integration.md` §2 (SP2, SP4), §6 (P4.1)
- **Triage-ID:** `trg-c57c0175`
- **Risk flags:** `touches_io_boundary` (hooks.json ×12 + `*_config.json` reads)

## Intent

Two shared bootstrap prompts + a hook wave so every session in a Shipwright
project knows the lay of the land without the user prefixing `/shipwright-iterate`.

- **SP2 — using-shipwright bootstrap:** a SessionStart hook injects
  `shared/prompts/using-shipwright.md` as `additionalContext` when
  `shipwright_run_config.json` is present in the project root. Silent in
  non-Shipwright projects. Once-per-session deduped (fires in all 12 plugins).
- **SP4 — writing-plugin gate:** a PostToolUse(mark) → Stop(gate) wave (exactly
  analogous to A.foundation A3's `check_file_size.py` + `bloat_gate_on_stop.py`):
  when a plugin-side file is edited, the Stop hook surfaces a once-per-session
  reminder to run `scripts/update-marketplace.sh` + `scripts/check_plugin_cache_sync.py`,
  AND appends an idempotent triage item so the reminder survives the session.

## Spec Impact

ADD (new prompts + new hooks + new registrations). No existing spec.md modified
(this is framework-internal tooling, not a target-project feature).

## Affected Boundaries

- **`plugins/*/hooks/hooks.json` (×12)** — registers 3 new hook commands each
  (SessionStart + PostToolUse Write|Edit + Stop). JSON I/O boundary.
- **SessionStart hook output** — `hookSpecificOutput.additionalContext` schema.
- **Stop hook output** — top-level `{"decision":"block","reason":...}` schema
  (no `hookSpecificOutput` wrapper — Stop schema, refreshed 2026-05-25).
- **PostToolUse stdin** — `tool_input.file_path` parsing.
- **Session markers** — `.shipwright/locks/using_shipwright_bootstrap.<sid>`,
  `.shipwright/locks/plugin_edit_pending.<sid>.json`,
  `.shipwright/locks/plugin_sync_reminded.<sid>`.
- **`.shipwright/triage.jsonl`** — new `source="plugin-sync"` producer.

## Files

| File | Action | LOC cap |
|---|---|---|
| `shared/prompts/using-shipwright.md` | NEW | ≤300 (runtime-prompt) |
| `shared/prompts/writing-plugin.md` | NEW | ≤300 (runtime-prompt) |
| `shared/scripts/hooks/session_start_using_shipwright.py` | NEW | ≤300 (source) |
| `shared/scripts/hooks/mark_plugin_edit.py` | NEW | ≤300 |
| `shared/scripts/hooks/plugin_sync_reminder_on_stop.py` | NEW | ≤300 |
| `plugins/*/hooks/hooks.json` | MODIFY ×12 (idempotent register) | — |
| `shared/tests/test_using_shipwright_hook.py` | NEW | ≤300 |
| `docs/hooks-and-pipeline.md` | MODIFY (hooks registry) | — |
| `docs/guide.md` | MODIFY (Ch.8 quality gates note) | — |

## Decisions (deviations from literal spec text)

1. **SessionStart hook is Python (`.py`), not `.sh`** (spec named `.sh`).
   Rationale: fires in all 12 plugins → needs atomic O_EXCL once-per-session
   dedup; must JSON-escape a whole markdown file into `additionalContext`;
   Windows-runtime robustness; consistency with the 4 existing Python
   SessionStart hooks invoked via `uv run`. Logged in decision_log.
2. **SP4 reminder = block-once-per-session + triage item**, not block-until-green.
   Rationale: block-until-green hard-loops when you've edited-but-not-pushed or
   the cache is absent (CI). Block-once "surfaces a reminder" (the operative
   acceptance wording) without ever bricking the agent; the triage item is the
   durable follow-up. User-confirmed 2026-05-29.
3. **"Plugin-side" = under `plugins/`, under `shared/` (excl. `shared/tests/`),
   or basename `SKILL.md`.** Broader than CLAUDE.md's `shared/scripts/` because
   `update-marketplace.sh` syncs ALL of `shared/` into the cache; `shared/tests/`
   excluded because tests are not loaded at runtime.
4. **SP4 is monorepo-scoped** (review-driven). Gated on
   `scripts/update-marketplace.sh` existing, so end-user projects (which have a
   `shipwright_run_config.json` but not that script) never get a reminder for a
   command they don't have. SP2 still fires everywhere (orientation is universal).
5. **Session id sourced from the hook stdin payload** (review-driven, was HIGH bug).
   `SHIPWRIGHT_SESSION_ID` is unset in sibling SessionStart hook processes, so an
   env-keyed sentinel would bootstrap only the first session ever. The payload's
   `session_id` is the canonical per-session key (same value across the 12 firings,
   rotates each session) — matches `capture_session_id.py`.

## Acceptance

1. Fresh session with `shipwright_run_config.json` present → asking "how do I add
   a feature?" returns `/shipwright-iterate` without prior priming (proxy:
   SessionStart hook emits `additionalContext` containing the iterate routing).
2. Fresh session in a non-Shipwright project → SessionStart hook stays silent.
3. Edit to `plugins/*/skills/*/SKILL.md` → Stop event surfaces a reminder to run
   `update-marketplace.sh` + `check_plugin_cache_sync.py` AND appends a triage item.
4. 12 hooks.json registrations idempotent (forward + reverse registry meta-test).

## Confidence Calibration
- **Boundaries touched:** hooks.json ×12 (JSON I/O), SessionStart/Stop/PostToolUse
  hook stdin+stdout schemas, session marker files, `.shipwright/triage.jsonl`.
- **Empirical probes run (subprocess, real stdin/env/cwd — Step 7.5):**
  1. SP2 on a Shipwright project → emits `hookSpecificOutput.additionalContext`
     containing `/shipwright-iterate`. **PASS**
  2. SP2 second fire, same session → empty stdout (O_EXCL dedup; 12×-fire safe). **PASS**
  3. SP2 on a non-Shipwright project → empty stdout (no false trigger). **PASS**
  4. SP4 `mark_plugin_edit` on `plugins/.../SKILL.md` → marker records the rel path. **PASS**
  5. SP4 Stop reminder → `{"decision":"block",...}` with `update-marketplace.sh`
     AND `check_plugin_cache_sync.py`. **PASS**
  6. SP4 Stop reminder → files a `source="plugin-sync"` triage item. **PASS**
  7. SP4 Stop reminder second fire → empty (block-once, no hard loop). **PASS**
  8. SP4 `mark_plugin_edit` on `docs/guide.md` → no marker (non-plugin-side). **PASS**
  Plus: 57 unit/registry tests green; 12 hooks.json round-trip json.load; registry
  re-run shows all-exactly-once (idempotent).
- **Edge cases NOT probed + why acceptable:** the live "fresh session answers
  correctly" behavior cannot run in THIS session — new hooks are inert until
  `update-marketplace.sh` syncs them to the cache + a new session starts (Fix-Now
  hint). Verified via the additionalContext-emission proxy (probe 1) + post-merge
  first session. Concurrent O_EXCL race across 12 parallel firings not stress-tested
  (single-winner semantics proven by the atomic create + the dedup probe).
- **Confidence-pattern check (asymptote):** the "works once" trap for N-times-per-event
  hooks was the prime risk → explicitly probed dedup (#2), block-once (#7), and
  idempotent registration/marker/triage. No yes-then-bug pattern surfaced.
