# Mini-Plan — iterate-2026-08-05-wire-local-guard-scripts

## Chosen approach

Two independent wirings, one stated rule. They share no code and can be
reviewed separately; they ship in one PR because they answer one card.

### Track 1 — `verify_local.py` into F0 (AC-1, AC-2)

1. **`plugins/shipwright-iterate/skills/iterate/references/F0.md`** — insert a
   step between the leak-guard and "Which command":

   > **Mirrored merge gates (if the project has them).** When
   > `scripts/verify_local.py` exists, run it before the suite — it is the
   > `ci.yml` guards nothing else runs locally, and at ~8 s it fails fast where
   > the suite takes minutes. Non-zero = **STOP**.
   > ```bash
   > uv run "{project_root}/scripts/verify_local.py"
   > ```
   > Absent (the normal case for an adopted project) → skip silently.

   Placement is *before* the suite deliberately: these gates are usually red for
   structural reasons an operator fixes in seconds, and learning that at 0:08
   instead of 7:00 is the round-trip the card exists to remove. Correctness is
   order-independent — the gates read the working tree, which F0 does not mutate
   (its own artefacts are gitignored).

2. **`SKILL.md`** F0 one-liner — extend "Leak-guard …, then full test suite" to
   name the mirrored gates, so the inline summary does not contradict `F0.md`.

3. **Tests** (`shared/tests/test_verify_local_ci_drift.py`, the existing home
   for this script's drift guards): assert `F0.md` carries the step, the
   existence guard, and the exact command; and that it precedes the suite
   section. Anchor-drift pattern, as `test_skill_step_6_rules_present.py`.

### Track 2 — `check_required_checks.py` into the producer chain (AC-3, AC-4)

4. **New `shared/scripts/hooks/check_required_checks_hook.py`** — thin wrapper,
   modelled on `check_drift.py`'s `main()`:
   - resolve the root via `lib.project_root.resolve_project_root()`, falling
     back to `os.getcwd()`;
   - no-op outside a Shipwright-managed project (same guard `check_drift` uses,
     so it cannot nag in an unrelated directory);
   - drive the producer and let it file its own card — the wrapper adds no
     triage logic of its own (single Producer per artifact);
   - **always exit 0, always print nothing.** `gh` absent/unauthed/unreachable
     (producer `exit 2`) and any unexpected exception are swallowed.

   Driven as a **subprocess**, not imported: `check_required_checks.py` does an
   eager module-scope `sys.path.insert` + `from lib…` / `from triage import…`,
   and binding `lib` inside a hook process is the ADR-045 collision that reads
   green locally and red in CI. `verify_local.py` made the same call for the
   same reason.

5. **`plugins/shipwright-iterate/hooks/hooks.json`** — append the wrapper to the
   SessionStart chain after `import_github_findings.py` (network producers keep
   their existing relative order; `capture_session_id.py` stays first).
   `shipwright-iterate` is deliberately **not** in
   `test_phase_plugin_hooks_consistency.PHASE_PLUGINS`, so this does not oblige
   the other 8 plugins to carry it.

6. **Tests** (`shared/tests/`): wrapper exits 0 and prints nothing with `gh`
   absent; wrapper is a no-op outside a Shipwright project; wrapper reaches the
   producer and a drift card is filed in a fixture repo (reusing
   `_required_checks_fakes.py`); hooks.json registers it.

7. **Integration test (AC-6, `cross_component` — non-dodgeable).** Drive the
   real `run_if_cache_ready.py` with the new hook registered, `gh` forced
   absent, and assert: the chain completes, exit 0, and stdout stays
   schema-valid. This is the composition the flag demands — wrapper + chain +
   producer together, not three units in isolation.

### Track 3 — honesty + docs (AC-5)

8. `scripts/verify_local.py` docstring: replace *"Nothing invokes this for you …
   tracked as trg-486cb11c"* with what is now true.
9. `CLAUDE.md`: *"Nothing runs it for you; it is a command you type."* → F0 runs
   it; typing it stays valid outside an iterate.
10. `docs/hooks-and-pipeline.md`: hooks-registry row for the new SessionStart
    producer (mandatory — CLAUDE.md requires a hook change to update it in the
    same diff). Check `docs/guide.md` Ch. 8.
11. After merge: `bash scripts/update-marketplace.sh` +
    `uv run scripts/check_plugin_cache_sync.py --strict` — a `hooks.json` /
    `F0.md` change does not reach the runtime cache otherwise.

## Alternative considered — one uniform answer: blocking `scripts/hooks/pre-push`

Both scripts behind one blocking pre-push hook. **Rejected**, three reasons:

- It **preserves the divergence `verify_local.py` documents about itself** — the
  gates read the working tree, but at push time the commit already exists and
  can differ from the tree. F0 is the one moment those coincide.
- It makes a **producer into a gate**. `check_required_checks.py` returns 0 on
  drift by design; a blocking hook would have to invent a failure, and it would
  refuse a push for a repository-configuration problem that has nothing to do
  with the diff in hand.
- It **collides with F11's delivery machinery** and can refuse a legitimate
  repair push, while the constitution forbids `--no-verify`. The escape would
  have to be a bypass env var, which is `--no-verify` with extra steps.

The advisory variant fixes the blocking cost but keeps the timing that makes it
pointless: by the time it prints, the push has happened.

## External plan review — response

Two providers (`openai` = **revise**, `deepseek` = **approve**; agree within one
step, no contradiction). Every finding is answered; six change the plan.

| # | Finding | Response |
|---|---|---|
| GPT-1 (high) | Cache sync scheduled after merge → PR inert or fails cache-sync validation | **Premise corrected, substance adopted.** `check_plugin_cache_sync.py` appears nowhere in `.github/` — there is no CI gate to fail, and the cache is a user-local directory (`~/.claude/plugins/cache/`), not a committed artifact, so no generated file belongs in this PR. The true part — the wiring is **inert at runtime until the re-sync runs** — is step 11 and is called out in the PR body and F12 summary. |
| GPT-2 (med) | F0 guard is prose while the snippet is unconditional; the anchor test could pass on nearby words | **Adopted.** The guard moves **into** the executable snippet (`if [ -f … ]`), run from the resolved project root. The drift test asserts the conditional structure and the ordering vs the suite section — not adjacent prose. |
| GPT-3 (med) | Subprocess contract underspecified (cwd, interpreter, absolute path, args) | **Adopted.** `sys.executable` + producer path derived absolutely from the wrapper's own location, `cwd=<resolved root>`, explicit `--project-root`, argv list. Test drives the registered hook from a **non-root cwd**. |
| GPT-4 (med) | stdout silence ≠ silence; child stderr leaks, `gh` can stall, catching everything hides a broken wrapper | **Adopted, and sharpened by a fact the reviewers lacked:** `run_if_cache_ready.py:114-116` forwards child stderr **verbatim** to the user. So the wrapper captures the producer's stdout *and* stderr, sets a bounded `timeout`, and catches `Exception` (never `BaseException`/`KeyboardInterrupt`). The operator-signal gap is closed **without a log file**: one line to the wrapper's *own* stderr on an unexpected failure reaches the operator through that same path, while stdout stays schema-clean. |
| GPT-5 (med) | Repeated sessions may duplicate cards; untested | **Adopted as a test.** The producer already uses `append_triage_item_idempotent` with a `dedup_key` and `match_commit=False`, so it is idempotent by construction — but that is exactly the claim to prove now that it runs every session. Test: run twice against one fixture drift, assert one card. |
| GPT-6 (low) | Command construction / credential leakage | **Adopted.** `shell=False`, fixed argv, no interpolation of project or repo values; captured output is discarded rather than echoed, so `gh` diagnostics cannot reach a triage card. |
| DS-3 (low) | `ImportError` on `lib.project_root` not explicitly handled | **Adopted** — caught explicitly, wrapper degrades to `os.getcwd()` like `check_drift`. |
| DS-1/2/4/5 | stderr, timeout, `--project-root`, operator signal | Subsumed by GPT-3/4 above; all adopted. |

## Rollback

Each track is one commit-scoped edit and reverts independently: remove the
`F0.md` step (Track 1), or drop the hooks.json line and delete the wrapper
(Track 2). Neither checker's own behaviour is modified, so reverting the wiring
restores today's state exactly.

## Risks

| Risk | Mitigation |
|---|---|
| The new hook slows or breaks session start | Fail-soft + silent by construction (AC-4), proven by the integration test (AC-6). Measured cost 1.5 s. |
| 3 `gh` API calls per session in consumer projects | Accepted: the producer is portable and the precedent (`import_github_findings.py`) already makes network calls in this exact chain. Fail-soft covers no-`gh` hosts. |
| `F0.md` prose is skipped by an agent | Accepted and named as a non-goal. The in-code alternative is bloat-blocked (518/518); the leak-guard shows the pattern works. |
| Plugin cache not re-synced → wiring inert at runtime | Step 11, plus `check_plugin_cache_sync.py --strict`. |
