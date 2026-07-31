# Mini-Plan: accepted-risk gate holes

- **Run ID:** iterate-2026-07-31-accepted-risk-gate-holes
- **Spec:** `iterate-2026-07-31-accepted-risk-gate-holes.md`

## Files to create/modify

| File | Change |
|---|---|
| `shared/scripts/accepted_risks.py` | edit — promote `_coerce_date` → public `coerce_date` (a sibling leaf now needs it; a third copy of the same parser would be worse). Docstring: absent register reads as empty **and is reconciled like one**. |
| `shared/scripts/accepted_risk_scan.py` | edit — honour each ignore entry's own expiry in both file forms; thread an optional `now`. |
| `shared/scripts/tools/accepted_risks_cli.py` | edit — `cmd_check` reconciles unconditionally; report the absent register instead of returning on it. `reconcile()` additionally returns what it discovered. |
| `plugins/shipwright-compliance/scripts/lib/accepted_risk_view.py` | edit — one line: pass the caller's `now` into discovery, so the dashboard stays deterministic. |
| `shared/tests/test_accepted_risks_cli.py` | edit — update the two absent-register cases; add the new discovery/expiry cases. |
| `shared/tests/test_accepted_risks_register.py` | edit — add the gate-level negative controls (holes 1 and 2). |
| `plugins/shipwright-compliance/tests/test_accepted_risk_view.py` | edit — the `now`-threading case; fix the one test that asserted a now-unreachable state. |
| `docs/security-ci-setup.md` | edit — document that an absent register no longer passes, and that a lapsed ignore entry is not a suppression. |
| `docs/hooks-and-pipeline.md` | edit — artifact-matrix row for `shipwright_accepted_risks.yaml` describes this gate's semantics. |

## Work breakdown

1. **`coerce_date` promotion** — rename in `accepted_risks.py`, update its two
   internal call sites. *Test:* existing `shared/tests/test_accepted_risks.py`
   stays green (no behaviour change).
2. **Entry expiry in `accepted_risk_scan`** — a `_lapsed(value, now)` predicate;
   YAML branch skips `expired_at <= now`; flat branch splits fields, takes
   field 0 as the id and honours an `exp:` field. `read_trivyignore_ids` and
   `discovered_suppressions` take `now: date | None = None`.
   *Test:* AC-3, AC-5, and the boundary + fail-safe rows of the ledger.
3. **`cmd_check` unconditional reconcile** — drop the early return; carry
   `discovered` out of `reconcile()` so the count is not re-read from disk;
   print the absent-register fact rather than exiting on it.
   *Test:* AC-1, AC-2, AC-4.
4. **`now`-threading in the dashboard view** — `discovered_suppressions(root,
   now=now)`. *Test:* AC-6.
5. **Docs** — the two prose sources that state this gate's contract.

## Data model changes

None. No schema, no new field, no migration. `SCHEMA_VERSION` is untouched:
the register format does not change, only what the reader does with the
**scanner's** file.

## Test strategy

- `shared/tests` — the gate itself (both halves: live guards over the real repo,
  negative controls over synthetic repos) plus the CLI's operator-facing output.
- `plugins/shipwright-compliance/tests` — the dashboard view's determinism.
- Both are separate pytest roots and MUST be run as separate invocations; the
  repo-root `conftest.py` exits 4 on a composed run (ADR-044). Running only
  `shared/tests` here would be a false green, since step 4 lands in the
  compliance plugin.
- No E2E: there is no web surface. F0.5 runs the CLI surface (see spec).

## Alternative approach (considered, rejected)

**Keep the early return and add a repo-level invariant instead** — i.e. do what
the downstream repo already does: a separate test asserting "this repo's
register exists and is non-empty".

Rejected. It is the workaround the finding names, and it fails in exactly the
case that matters: a contributor removing the register in the same change that
removes the invariant test passes CI, and every suppression stays live and
unrecorded. It also does not travel — every consuming repo would have to
re-invent the same backstop, and a gate that only works when a second, deletable
test is present is not a gate. Making `check` answer its own question needs
strictly less machinery than a guard that protects the guard.

A second alternative — **treat a lapsed ignore entry as *drift* rather than as
absent** (keep it in discovery, report a new `LAPSED` class) — was rejected as
scope the brief deliberately excludes: it invents reporting vocabulary, which is
the SecFix-5 conversation. Treating a lapsed entry as absent needs no new
vocabulary: it already surfaces as `STALE`, which is exactly what it is.
