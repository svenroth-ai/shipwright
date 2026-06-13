# Mini-Plan: Interleaved-serial as the single documented campaign default

**Run ID:** `iterate-2026-06-13-campaign-serial-default` · Intent: CHANGE · Complexity: medium

## Chosen approach

New `branch_strategy` value **`serial`** (base = fresh `origin/main`,
merge-before-next), made the `campaign_init` default. The autonomous campaign
loop is restructured to **interleaved-serial**: build ONE sub-iterate → open PR →
wait CI green → merge → advance local `main` → build NEXT from fresh
`origin/main`. The end-stage "Serial Merge Drain" is retired.

## Alternative considered & rejected

Reinterpret the existing `independent` strategy as interleaved (no new value,
smaller diff). Rejected: "independent" implies parallel/order-independent, which
contradicts the merge-before-next contract — misleading for a human reading the
docs. A clearly-named `serial` value matches the goal (unambiguous for agent +
human). Cost: one additive branch in `cmd_next`. Worth it.

## Why parallel never works for campaigns (rationale)

Campaign sub-iterates each regenerate shared *derived* artifacts (events.jsonl,
triage.jsonl, compliance MDs, dashboard). Even file-disjoint sub-iterates collide
on these churn snapshots → parallel build-all-then-drain ALWAYS degrades to
drain+regenerate (`ensure_current`) = merge theater. Build sidesteps this by
shipping ONE PR (`single-branch`), so its sequential/end-merge model is fine.
Hence serial is the only structurally-safe campaign model — retire the parallel path.

## Steps (TDD)

1. `autonomous_loop.py`: `VALID_STRATEGIES += "serial"`; `cmd_next` serial →
   `base_branch="main"` (additive; build's `stacked`/`single-branch` untouched).
   Test: `test_autonomous_loop.py::test_serial_provides_main_base`.
2. `campaign_init.py`: `--branch-strategy` default `serial`, choices
   `[serial,stacked,independent]`; `init_campaign` default param `serial`.
   Update `test_campaign.py` default assertions stacked→serial.
3. `campaign-mode.md`: restructure loop to interleaved (build→merge(CI-green)→
   advance main→next); serial setup/init examples; retire end-stage drain.
4. `SKILL.md §5b` + F11 index row; `F11.md` campaign prose; `sub-iterate-runner.md`
   base = fresh `origin/main`. Preserve `SHIPWRIGHT_ITERATE_AUTOMERGE=0` defer.
5. Rewrite `test_campaign_serial_drain.py` → pin interleaved sequence; verify
   `test_f11_automerge_arm.py` defer asserts stay green.
6. Add `category:"integration"` test: serial loop init→next→record→next, each off
   fresh `main`, one-at-a-time (satisfies cross_component gate).
7. Check `docs/guide.md` + `docs/hooks-and-pipeline.md` for strategy/drain refs.

## Safety

- `autonomous_loop.py` shared with build → additive only.
- `cross_component` F11 gate (`check_integration_coverage`) satisfied by step 6.
- F11 refresh-if-behind guard kept (general per-iterate; harmless no-op under serial).
