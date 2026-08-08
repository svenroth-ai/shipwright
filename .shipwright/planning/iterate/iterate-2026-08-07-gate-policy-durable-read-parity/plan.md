# Mini-plan — P2.41a: gate_policy read-leg parity

## Approach

1. **`shared/scripts/lib/gate_policy.py`** — `read_run_config_mode` now reads
   the config via `lib.atomic_write.durable_read_text` (a lazy, function-local
   import) instead of a plain `(Path(...) / _CONFIG_NAME).read_text(...)`.
   This mirrors the already-established `from lib.atomic_write import
   durable_atomic_write` sibling-import precedent in `lib.adr_index` (same
   package, same sys.path resolution via `shared/scripts` — verified both
   resolve identically under `shared/tests/conftest.py`'s sys.path setup and
   under `resolve_gate_policy.py`'s CLI setup). The existing
   `except (ValueError, OSError, RecursionError, TypeError)` guard already
   covers the eventual `PermissionError` `durable_read_text` re-raises past
   its retry budget (a `PermissionError` is an `OSError`), so the fail-safe
   direction is unchanged — only the *retry* behavior changes.

2. **Bloat budget** — `gate_policy.py` is grandfathered in
   `shipwright_bloat_baseline.json` at `current: 301` / `limit: 300`: zero
   headroom. Per prior guidance on this exact file
   (`feedback_bloat_cap_at_current_forces_design`), raising `current` to fit
   is not an option. The +1 net line for the import was offset by removing
   one line that was genuinely redundant with its own function's docstring
   (`validate_catalog`'s inline `# The core safety invariant.` comment,
   already stated in the docstring two lines above it) — net line count
   unchanged (301 → 301).

3. **`plugins/shipwright-run/scripts/lib/orchestrator_pkg/config_io.py`** —
   the "Mode" comment block that explicitly documented this exact gap as
   deliberately open is updated to describe the closed state and the fix
   (lazy sibling import, same retry primitive). No behavior change in this
   file — comment-only.

4. **Tests** — split by what each one actually needs (internal Opus plan
   review, finding 2), not bundled into the plugin tree by default:
   - `shared/tests/test_gate_policy.py`: one stale cross-reference sentence
     updated (was pointing at the still-open gap; now points at the closed
     one). No test logic changed.
   - New `shared/tests/test_gate_policy_read_retry.py` (pure `lib.gate_policy`
     + `lib.atomic_write`, no plugin dependency): (a) the reporter survives a
     simulated Windows delete-pending read and still resolves
     `SINGLE_SESSION`; (b) the fail-safe boundary still holds past the retry
     budget.
   - New `plugins/shipwright-run/tests/test_runconfig_read_retry_parity.py`
     (plugin-side ONLY because it needs both `orchestrator_pkg.config_io` AND
     `lib.gate_policy` in the same process — unavailable to `shared/tests`,
     ADR-044): the direct parity test — the orchestrator loop and the gate
     mechanism agree under an *identical* simulated race, replayed against
     each reader in turn. Its `shared/scripts` sys.path insert is now
     explicit rather than relied on as a side effect of `import orchestrator`
     (finding 3).

   Verified the read-retry test and the parity test FAIL without the fix
   (temporarily reverted `gate_policy.py` via `git stash`) and PASS with it,
   both before and after the split.

   Note: `config_io.durable_read_text` and `gate_policy`'s new
   `lib.atomic_write.durable_read_text` are two distinct Python module
   instances of the same source file (the plugin bridges via a top-level
   `atomic_write` import in `run_config_store.py`; `shared/` code bridges via
   `lib.atomic_write`) — a pre-existing, harmless ADR-045-shaped duplicate
   load. The parity test patches both module instances' `_is_windows`; `time`
   is the same global stdlib module either way, so it is patched once.

## Alternative considered

Route `gate_policy.py` through `orchestrator_pkg.run_config_store` instead of
importing `atomic_write` directly. Rejected: `shared/` must never import a
plugin (`gate_policy.py`'s own header already states this — "shared can't
import a plugin", mirroring `orchestrator_pkg.constants`), so this was never
viable; the sibling `lib.atomic_write` import is the only architecturally
sound route.

## Risk

Low, with one caveat raised by internal Opus plan review before commit, then
superseded by doubt-reviewer (see the Doubt Review table below): the lazy
`from lib.atomic_write import durable_read_text` inside the function's own
`try:` block could raise `ImportError` in a hypothetical caller context where
`lib` resolves to a different package (no *current* caller does this — every
importer of `gate_policy` loads it as `lib.gate_policy`, which guarantees
`lib` already means `shared/scripts/lib` — but the function's docstring
promises it is TOTAL at the read boundary, and a latent trap under a safety
control is still a trap). The first fix caught `ImportError` alongside the
existing tuple; doubt-reviewer found that fix itself flawed — it traded the
only diagnostic signal for a misreport indistinguishable from a legitimate
`INERT_MODE` — so the import is module-level instead (same as every sibling
`shared/scripts/lib` importer of `atomic_write`), loud on a broken install
like the rest of the package, at the same zero line-budget cost.

Two more caveats, disclosed rather than mitigated (both accepted as-is —
they describe what the fix intentionally does, not a defect):

- **Latency:** `read_run_config_mode` was previously bounded by one
  `Path.read_text`; it can now block for up to `READ_RETRY_BUDGET_SECONDS`
  (2.0s) per call on Windows under contention. That is the cost of parity,
  not a bug — no hook or CLI wrapping `resolve_gate_policy.py` enforces a
  tighter timeout (`hooks.json` in this plugin carries no timeout on the
  gate-resolution path).
- **Direction of the fix:** it deliberately makes the reporter answer the
  *permissive* value (`SINGLE_SESSION`, which activates auto-answering of
  `auto-default` gates) during a race window where it previously answered
  the conservative `INERT_MODE` — because the orchestrator's answer is
  authoritative, and disagreement (not permissiveness) is the actual hazard
  P2.41a exists to close. The exhausted-budget path (a genuinely stuck
  holder) still degrades to `INERT_MODE`, so a config that is unreadable for
  reasons *other* than a transient concurrent rewrite is unaffected.

No `docs/hooks-and-pipeline.md` update: this diff changes HOW the config is
read, not WHAT is read, and touches no hook, phase validator, or
between-phase action.

## Doubt Review (Stage 3, fresh-context adversarial)

| # | Finding | Severity | Disposition |
|---|---|---|---|
| D-1 | The lazy `try:`-scoped import + `ImportError` catch (from the internal Opus fold-in) contradicts the 4 other `shared/scripts/lib` siblings that all import `atomic_write` at module level (loud on failure), and silently converts an environment/packaging fault into a misreport indistinguishable from a legitimately mode-less config — also contradicting `resolve_gate_policy.py`'s own precedent of warning on stderr for a similar degrade-safely case, and the documented consumer contract in `shared/prompts/single-session-gate-discipline.md` ("fail safe, not fail-blocking... behave interactively"). | high | **fixed**: reverted to a plain module-level `from lib.atomic_write import durable_read_text` import; `ImportError` removed from the except tuple; docstring's "unresolvable import" clause removed. Verified module-level costs the identical 1 net line as the lazy version once the offsetting `validate_catalog` comment removal (§2) is counted — file is still exactly 301 lines. |
| D-2 | The "LOCKSTEP with `config_io._read_parse_shape`" docstring claim overstates parity past retry-budget exhaustion: a genuinely stuck holder makes `read_run_config_mode` degrade to `INERT_MODE` while `config_io`'s strict reader still raises/re-raises. | medium | **fixed**: docstring now reads "LOCKSTEP ... within the retry budget" (`gate_policy.py`); `config_io.py`'s Mode comment block gained a paragraph making the post-budget divergence explicit (disposal asymmetry was already partly documented, the retry-budget qualifier was not). |
| D-3 | `config_io.py`'s Mode comment (written earlier this run) contains two factual errors: it claims this module reads via `lib.atomic_write.durable_read_text` (it actually reaches `durable_read_text` through the top-level `atomic_write` import in `run_config_store.py`), and it names the wrong sys.path directory (`shared/scripts/lib` where `shared/scripts`, the parent, is what `lib.atomic_write` needs — `shared/scripts/lib` on sys.path is what gives the *top-level* `atomic_write` this module uses). | high | **fixed**: rewrote the block to correctly attribute each reader's import path and each directory's role; independently re-verified against `run_config_store.py:49`'s actual import statement and against which sys.path entry each import form requires. |
| D-4 | The parity claim silently assumes `mode` is write-once (never mutated in place post-creation) — undocumented, and load-bearing for the "same settled value" framing. | low | **fixed**: `config_io.py`'s Mode block now states the write-once assumption explicitly. |
| D-5 | `test_runconfig_read_retry_parity.py`'s second `_flaky_read_text(flips=2)` call captures `Path.read_text` for its "real" fallback AFTER the first call already monkeypatched it — so it closes over the first flaky wrapper, not the genuine original. Passes today only because of accumulated counter state, not by correct construction. | medium | **fixed**: `Path.read_text` is now captured once into a module-level `_REAL_READ_TEXT` at import time, before either test can monkeypatch it; both flaky wrappers close over that instead of a call-time `Path.read_text` lookup. |

No findings rejected — all five addressed. Re-verified after fixes: both new
regression tests (`shared/tests/test_gate_policy_read_retry.py`) and the
parity test still FAIL under `git stash` (pre-fix `gate_policy.py`) and PASS
against the fixed tree; `shared/tests/test_gate_policy.py`,
`shared/tests/test_atomic_write_windows_read_retry.py`, and the full
`plugins/shipwright-run` suite re-run green; lint clean; bloat baseline
unchanged (`gate_policy.py` still exactly 301 lines).

## External LLM Review (Branch A, openrouter — GPT-5.6 + DeepSeek)

Verdicts: DeepSeek `approve`; GPT-5.6 `revise` (no contradiction — within one
step of each other). Findings and disposition:

| # | Finding | Severity | Disposition |
|---|---|---|---|
| GPT-1 / DS-1 | Plan doesn't restate that `durable_read_text` is called with the same explicit `encoding="utf-8-sig"` as before / as `config_io` | medium/low | **rejected-with-reason**: both reviewers saw only `plan.md`'s prose, not the diff — the actual call already passes `encoding="utf-8-sig"` verbatim (`gate_policy.py:159`), identical to the pre-fix code and to `config_io`'s own call. Empirically pinned by the pre-existing, still-green `test_read_run_config_mode_tolerates_a_utf8_bom` and `test_read_run_config_mode_round_trips_every_written_mode`. Documented here so the plan text itself now states it (this table). |
| GPT-2 | Retry-clock simulation could be timing-sensitive / needs a fake clock | medium | **rejected-with-reason**: `test_read_run_config_mode_still_fails_safe_past_the_retry_budget` doesn't patch `time.sleep`, matching the EXISTING precedent (`test_atomic_write_windows_read_retry.py::test_read_gives_up_loudly_rather_than_inventing_an_empty_config` does the same) — a 0.02s budget bounds total real sleep to ≤0.02s, so it is fast and non-flaky without a fake clock. Not a new pattern. |
| GPT-3 | Add a smoke test that the import resolves to the intended `atomic_write.py` at each production entry point | low | **rejected-with-reason**: every passing test already IS that smoke test — `read_run_config_mode` only returns `SINGLE_SESSION`/`INERT_MODE`-from-content (not from an import failure) when the import genuinely resolved; an unresolvable import would make every test in both new files fail with the reporter degrading to `INERT_MODE` regardless of file content, which none of the content-based assertions would tolerate. |
| GPT-4 | Parity test should assert the observable contract, not implementation | low | **already satisfied**: the parity test asserts `SINGLE_SESSION`/`is_single_session`, never internal retry mechanics. |
| DS-2 | Note the 301-line zero-headroom constraint so a future maintainer isn't surprised | low | **accepted-and-fixed**: this plan (§2, "Bloat budget") and the self-review already document it; no source comment added (would itself cost the budget it's warning about). |
| DS-3 | `ImportError` guard doesn't cover a hypothetical `SyntaxError` from a corrupted `atomic_write.py` | low | **rejected-with-reason**, reviewer's own words: "negligible... no action required" — a corrupted checkout is an environment fault, not a config-content fault; crashing loudly there is correct, matching how every other `SyntaxError`-class failure in this codebase is treated. |
| DS-4 | ADR-045 duplicate-load seam is explained in-test, no change needed | low | **no change needed** (reviewer's own verdict). |

No high-severity findings from either reviewer. No code changes resulted;
one plan-clarity gap (encoding) closed by this table.

## External Code-Review Cascade (Branch A, openrouter — GPT-5.6 + DeepSeek)

Ran over the full staged diff (320 lines, `git diff HEAD`) against `spec.md`,
after the doubt-review fixes above landed. Both verdicts `approve`, no
contradiction, no findings from either reviewer.

**Follow-up (not done here, out of scope for a small fix):** the internal
review suggested extracting the ~26-line mode-resolution block
(`_CONFIG_NAME`, `SINGLE_SESSION`, `INERT_MODE`, `read_run_config_mode`,
`effective_mode`) out of `gate_policy.py` into its own module, both to give
it a natural home for its own shared-tests file and to retire the
zero-headroom pressure on `gate_policy.py` permanently instead of trading
one comment line at a time. Left for a future iterate — it is a structural
change with its own blast radius (every importer of these five names) and
not warranted by a two-line bug fix.
