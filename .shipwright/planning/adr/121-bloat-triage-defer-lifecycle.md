# ADR-121: Bloat exception — the triage park lifecycle raises eleven guarded ceilings

- **Status:** accepted
- **Date:** 2026-08-01
- **Re-Review-Date:** 2026-11-01
- **Incident Reference:** iterate `iterate-2026-08-01-triage-defer-lifecycle`,
  card `trg-49f354ad` (split from anchor `trg-4ebc928e`, content from
  `trg-51f8e2a1`). Operator decisions of 2026-07-27, recorded in
  `.shipwright/planning/iterate/2026-07-27-triage-defer-review-followup.md`.

## Context

`defer` recorded a decision that almost nothing downstream honoured: a parked
finding re-appeared as a **new** open entry on the next import, never closed
when the problem went away, was invisible to every surface but the terminal
listing, could not be reversed by any command, and printed uncapped. Closing
those five gaps is one coherent piece of work, and the operator asked for it
bundled rather than split five ways.

Eleven baseline entries move. Six move by one to three lines each — the
mechanical cost of every auto-resolving producer reading one declared answer to
"which statuses may I close?" instead of a copied literal:

These are deliberate exception raises, not a silent sliding ceiling. The
canonical `anti_ratchet_check.py` remediation explicitly permits a measured
raise when a bloat-exception ADR is written and the baseline is bumped in the
same commit; this ADR is that evidence.

| Path | current → new | Δ |
|---|---|---|
| `shared/scripts/hooks/check_drift.py` | 446 → 449 | +3 |
| `shared/scripts/lib/phase_quality/_triage_bundle.py` | 325 → 326 | +1 |
| `plugins/shipwright-compliance/scripts/lib/sbom_generator.py` | 548 → 550 | +2 |
| `plugins/shipwright-compliance/scripts/lib/test_evidence.py` | 931 → 932 | +1 |
| `plugins/shipwright-compliance/tests/test_sbom_generator.py` | 847 → 848 | +1 |
| `plugins/shipwright-compliance/tests/test_test_evidence.py` | 577 → 578 | +1 |
| **`shared/tests/test_triage_schema.py`** | 488 → 558 | **+70** |
| **`shared/tests/test_triage_defer.py`** | 240 → 366 | **+126** |
| **`shared/tests/test_triage_precondition_registry.py`** | 175 → 331 | **+156** |
| **`shared/scripts/triage.py`** | 837 → 882 | **+45** |
| **`shared/scripts/tools/triage_promote.py`** | 324 → 420 | **+96** |

The last five need the detailed arguments below. The six small ones are the
mechanical cost of one shared import (plus two refreshed comment lines in
`check_drift.py`), but they still move guarded ceilings: each is therefore an
ADR-121 exception in the baseline rather than a grandfathered ceiling silently
ratcheted upward.

`test_triage_schema.py`'s +70 is the wire-format coverage AC-17 and AC-19(a)
demanded and did not have: a park with a date validates, a park **without** one
still validates (the Command Center writes exactly that), `revisitAt` is
rejected on all three other statuses, five malformed date forms are rejected,
and — the case an external reviewer raised — the conditional is proven NOT to
constrain `reason`, without which `unpark` would be unrecordable and nothing
would have caught it. It is a test file: the honest comparison is not against
300 but against the alternative of shipping an `additionalProperties: false`
schema change with no test at all. **It is also on this table only because the
Stage-1 re-review found it** — my own anti-ratchet check had run before these
tests were appended, which is exactly how a ninth crossing gets smuggled past a
promise not to smuggle any.

`test_triage_defer.py` is the pre-existing decision-surface suite. Its +126
updates every old defer case for the now-required date and pins re-parking plus
the version-2 machine contract. Splitting those cases away would separate the
new contract from the tests that previously asserted its opposite.

`test_triage_precondition_registry.py` is a static whole-repository pin, not a
feature-behaviour suite. Its +156 teaches that pin to resolve the shared status
constants and to follow helper parameters through every caller; otherwise the
seven producer paths could appear registered while one supplied a different or
impossible status set. Keeping parser, resolver and assertions together makes
the registry's proof readable as one unit.

**What was paid for first.** The growth is the residue after the change moved
everything it could out of the capped files:

- the entire park *policy* — date parsing, expiry, ordering, the status
  vocabularies — went into a new `shared/scripts/lib/triage_defer.py` (~180 LOC),
  not into `triage.py`;
- the `list --json` contract shape went into a new
  `shared/scripts/lib/triage_contract.py`, not into `triage_cli.py`;
- the markdown renderer split out of `triage_render.py` into
  `triage_render_md.py` when that file crossed 300;
- `aggregate_triage.py` (ADR-090, ceiling 387) gained a whole new rendered
  section and stayed below that existing ceiling, because its private
  `_escape_md` / `_truncate` moved to the renderer modules where they belong —
  and that also killed a byte-identical duplicate clip function.

`triage.py`'s own +45 is the lock-bound clock and status-overlay code plus its
supporting docstrings/comments; an
earlier draft was +80 and was trimmed by moving the rationale into
`triage_defer.py` and leaving pointers.

## Ousterhout Argument

**`shared/scripts/triage.py`** — unchanged from ADR-100 and reinforced by this
change. It is a deep module: the interface is `append_triage_item`,
`append_triage_item_idempotent`, `mark_status`, `read_all_items` plus the outbox
routing surface, and behind it sit cross-process locking, header bootstrap,
tolerant JSONL parsing, dedup under lock, two-file union resolution, and now
expiry resolution. Expiry belongs *here* specifically because this is where
resolution already lives: putting it in the consumers would mean ten call sites
each deciding whether a park has come due, which is the drift the module exists
to prevent. What this change added is one call and one overlay; the rules
themselves are behind a second, genuinely narrow interface (`triage_defer`).
Splitting `triage.py` remains refused for ADR-100's reason: the lock, the path
helpers, the append writer and the union reader share invariants that only hold
when they are read and modified together.

**`shared/scripts/tools/triage_promote.py`** — this file's interface is four
verbs (`promote`, `dismiss`, `defer`, `unpark`) over one concept: *an operator
decides something about a finding*. Behind them sit input sanitising, the
existence check, the effective-status guard, the store's own precondition, and
one shared refusal wording. The +96 is the fourth verb plus a required argument
on the third — that is interface growth matched by behaviour, not padding.
Notably the shared body did **not** multiply: `dismiss`, `defer` and `unpark`
route through one `_transition`, which is why adding a whole verb cost what it
did rather than three times that. Splitting the verbs across files would put
four sites that must agree on one guard into four files, which is precisely the
failure mode the shared `_transition` and the single `_wrong_status_error` exist
to prevent.

## YAGNI Check

Walked each responsibility this change added:

- **Revisit date, required at the decision layer** — needed today; a park with
  no date is what let a deferral become permanent and what let a machine-raised
  finding duplicate on the next import. Deliberately NOT required at
  `mark_status`: the Command Center writes a date-less park and every
  pre-existing park has none.
- **Expiry by derivation** — needed today; the alternative (a sweep that writes
  the expiry) needs a scheduler that does not exist and leaves every surface
  stale until it runs.
- **`unpark`** — needed today; without it a mis-park pushes an operator to
  hand-edit `triage.jsonl`, the exact untrusted-input path the renderer defends
  against.
- **`AUTO_RESOLVABLE_STATUSES`** — needed today; seven producer paths must
  agree, and a copied literal in each is how they stop agreeing.
- **Contract version 2** — needed today; a parked entry has to be visible on the
  machine surface and a flat array has no sections.
- **Cap + total ordering** — needed today; an uncapped parked section crowds out
  open work, and without a total order "the first N" differs between runs.

Refused as speculative and recorded here so the refusals are auditable: a
`--json-version 1` compatibility flag (no known consumer; the operator accepted
an immediate break); a `storedStatus` field on the resolved view (the revisit
date already distinguishes an expired park from an un-parked entry); widening
`accepted_risks_converge` and the github legacy migration to close parked
entries (neither is a "the finding disappeared" resolver, and no decision on
record covers them).

Known boundary: Python writers share `FileLock`, but the Command Center uses
`proper-lockfile`; AC-9 therefore covers cooperating Python writers only.
Cross-repository lock/transition unification is tracked by `trg-97aeaede`.

## External-Code-Review-Findings

| Reviewer | Severity | Finding | Disposition |
|---|---|---|---|
| OpenAI | medium | `read_all_items(now=...)` derived the lifecycle day from the caller's timezone instead of UTC and accepted naive datetimes. | **accepted-and-fixed** — the store boundary now validates awareness and normalizes the instant to UTC; regressions cover a `+14:00` date boundary and a naive value. |
| OpenAI | low | The malformed-date CLI test did not assert AC-6's promised `YYYY-MM-DD` guidance. | **accepted-and-fixed** — every invalid-date case now asserts the accepted form in stderr. |
| Gemini | unavailable (truncated) | The partial response questioned why an expired park bypasses the producer recency cutoff. | **rejected-with-reason** — AC-5 and ledger row 6 explicitly require an expired park to suppress a duplicate even when the original predates that window; the complete regression is `test_an_expired_park_also_suppresses_because_it_is_open_again`. Gemini's response ended before a verdict. |

## Doubt-Review Dispositions

| Doubt | Disposition |
|---|---|
| Store header remains v1 although status events gain `revisitAt`. | **rebutted-with-boundary** — this is an optional additive key; the only supported runtime reader is tolerant and the only supported strict validator ships updated here. Rollback preserves every append-only event but temporarily leaves dated parks snoozed until re-upgrade, so the semantic addition is explicitly forward-only. |
| A version-1 CLI consumer cannot inspect `contractVersion: 2` before failing on the new top-level object. | **accepted operator trade-off** — decision 3 of 2026-07-27 explicitly accepted the immediate break and declined a speculative compatibility mode. WebUI card `trg-f2214310` records that runtime is unaffected today; its manually regenerated parity snapshot is the follow-up surface. |
| Two concurrent operator re-parks, or re-park versus unpark, are last-writer-wins. | **rebutted-with-existing-contract** — status resolution has always been append-order last-writer-wins. Both serialized events remain in the append-only audit log and either decision is recoverable by another explicit transition; this iterate promises producer-versus-operator preconditions, not CAS between two operators. |
| The schema accepted impossible calendar dates that the runtime rejects. | **accepted-and-fixed** — `revisitAt` now carries JSON Schema `format: date`, the canonical schema tests activate `FormatChecker`, and `2026-02-30` is pinned invalid. |

## Chesterton-Fence Check

The 837 fence on `triage.py` is ADR-100's, itself raised from a grandfathered
592. Its stated reason — one place where every triage producer and consumer
agrees on the wire format and the resolution rules — is exactly what this change
extends: a fifth resolution rule (a park expires) joins the four already there,
and every consumer inherits it without being touched. Tearing the fence down by
splitting would scatter those rules; raising it deliberately keeps them together
and keeps the raise on the record.

The 324 fence on `triage_promote.py` is a plain grandfathered size with no ADR —
a recorded crossing, not a reasoned boundary. Git history shows the file
accreting one operator decision at a time (promote, then dismiss, then defer,
each with its guard). This change adds the fourth and, in doing so, *reduced*
the per-verb cost by giving the three status-flipping verbs one body. The fence
was never load-bearing at 324; it is now recorded with a reason and a
re-review date rather than left as an unexplained number.
