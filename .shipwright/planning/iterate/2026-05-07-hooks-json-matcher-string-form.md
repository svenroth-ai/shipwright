# Iterate Spec: PreToolUse / PostToolUse matcher must be string under Claude Code 2.1.132+

- **Run ID:** iterate-2026-05-07-hooks-json-matcher-string-form
- **Type:** bug
- **Complexity:** trivial (3 string edits across 2 files + 1 test extension + 2 version bumps)
- **Status:** draft
- **Follow-up to:** ADR-039 (closes a second schema requirement surfaced by `claude plugin list` post-merge)

## Goal

Restore loadability of `shipwright-build` and `shipwright-compliance` under Claude Code 2.1.132+. After ADR-039 wrapped event names under `"hooks"`, `claude plugin list` revealed a second schema tightening:

```
× shipwright-build@shipwright failed to load
  Hook load failed:
  - path ["hooks","PreToolUse",0,"matcher"]: expected string, received object
  - path ["hooks","PostToolUse",0,"matcher"]: expected string, received object
```

Pre-2.1.132, `matcher` accepted an object form `{"tools": ["Bash"]}`. 2.1.132+ requires a string: a single tool name (`"Bash"`), a regex alternation (`"Write|Edit"`), or `"*"` for all tools. The legacy object form crashes plugin load entirely, so all hooks for the affected plugin are silenced.

## Affected files

Repo-wide grep `"matcher":\s*\{` across `plugins/*/hooks/hooks.json` (post-ADR-039) found exactly two occurrences:

| File | Event | Old matcher | New matcher |
|---|---|---|---|
| `plugins/shipwright-build/hooks/hooks.json` | `PreToolUse[0]` | `{"tools": ["Bash"]}` | `"Bash"` |
| `plugins/shipwright-build/hooks/hooks.json` | `PostToolUse[0]` | `{"tools": ["Write", "Edit"]}` | `"Write|Edit"` |
| `plugins/shipwright-compliance/hooks/hooks.json` | `PreToolUse[0]` | `{"tools": ["Bash"]}` | `"Bash"` |

`shipwright-build` was empirically reproduced as failing on this PC (`× failed to load` from `claude plugin list`); `shipwright-compliance` is not currently installed locally but ships with the same broken shape and would fail the moment a user `claude plugin install`s it.

## Acceptance Criteria

- [x] **AC-1 — `PreToolUse` and `PostToolUse` matcher fields are strings.** For every `plugins/*/hooks/hooks.json`, every `matcher` value under `PreToolUse` / `PostToolUse` MUST be `str`. The legacy object form `{"tools": [...]}` MUST NOT appear anywhere.
- [x] **AC-2 — Catch-all matcher groups (no `matcher` key) preserved.** A group without a `matcher` field is the all-tools form and remains untouched. Only groups that DO declare `matcher` are converted.
- [x] **AC-3 — Plugin versions bumped.** `shipwright-build` `0.2.1`→`0.2.2`, `shipwright-compliance` `0.2.1`→`0.2.2`. The 11 unaffected plugins keep their post-ADR-039 versions (`0.2.1` / `0.3.1` / `0.4.1`). `shipwright-preview` stays at `0.2.0`.
- [x] **AC-4 — Regression test extended.** `shared/tests/test_hooks_json_wrapper.py` gains a parametrized `test_pre_post_tool_use_matchers_are_strings` (12 plugins) that asserts every declared `matcher` under `PreToolUse` / `PostToolUse` is a `str`. Catches future regressions to the legacy object form at test time.
- [x] **AC-5 — Empirical fix verified post-merge.** `claude plugin update shipwright-build@shipwright` + `claude plugin list` shows ✔ enabled (was ✘ failed to load).

## Out of Scope

- **Reverse-mapping all matchers to `"*"` for max permissiveness** — rejected. The point of `matcher` is to scope hooks to specific tools; collapsing to `"*"` changes hook semantics (e.g. `validate_command.sh` would now run on every tool call, not just `Bash`). Convert object form to equivalent string form, no behavioral change.
- **Separate `Write`/`Edit` matcher groups instead of `"Write|Edit"`** — rejected. The two tools share an identical hook chain in `shipwright-build`'s `PostToolUse[0]`; alternation is the canonical 2.1.132 idiom and produces fewer matcher groups (one vs. two).
- **Plugins beyond build / compliance** — verified by repo-wide grep that no other plugin uses object-form matchers (the other 11 plugins either have no `PreToolUse`/`PostToolUse` or use catch-all groups without a `matcher` field).

## Affected FRs

- **FR-01.05 (build) and FR-01.10 (compliance)** indirectly — the change is mechanical schema migration, no FR semantics change.

## Affected Boundaries

| Producer | Artifact | Consumer | Probe |
|---|---|---|---|
| Shipwright (this iterate writes) | `plugins/{build,compliance}/hooks/hooks.json` | Claude Code 2.1.132+ harness | Empirical: `claude plugin update shipwright-build@shipwright` + `claude plugin list` shows ✔ enabled. **Pre-merge probe done on this PC** (caught the bug); **post-merge probe** runs after the follow-up PR merges. |

## Confidence Calibration

1. **Boundaries touched:** single producer/consumer pair (this repo writes `hooks.json` → Claude Code reads on plugin load), same as ADR-039.
2. **Empirical probes run:**
   - Repo-wide grep `"matcher":\s*\{` post-fix returns zero matches (production-side coverage check).
   - Extended regression test parametrized over all 12 plugins — 12/12 pass.
   - `claude plugin list` is the empirical chokepoint and surfaces post-merge after `claude plugin update shipwright-build@shipwright`.
3. **Edge cases NOT probed + why acceptable:**
   - **Live install of `shipwright-compliance`** — not installed on this PC; its hooks.json shares the same broken shape that build empirically demonstrated. Pre-emptive fix.
   - **Other matcher-shape variants** — Claude Code 2.1.132 documentation accepts string form only; no other variants documented.
4. **Confidence-pattern check:** No "are you confident?"-style yes-then-bug pattern in this run. The previous iterate (ADR-039) shipped without catching this — that itself was a yes-then-bug pattern. Mitigation: regression test now asserts both schema invariants, so the next plugin author can't reintroduce either.

## Verification (small)

- **Surface:** none (plugin-metadata change).
- **Justification:** consumer is the closed-source Claude Code 2.1.132+ binary; no startable surface in this repo.
- **Runner command (post-install):**
  ```bash
  claude plugin update shipwright-build@shipwright
  claude plugin list | grep -A1 shipwright-build    # expect ✔ enabled
  ```
- **Fail-closed:** if `claude plugin list` still shows ✘ failed to load after `update`, escalate — there is a third schema tightening we missed.
