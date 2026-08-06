# Mini-Plan — iterate-2026-08-05-it1-audit-remainder

Implementation steps for the ACs in `2026-08-05-it1-audit-remainder.md`.
TDD order: each step writes the failing test first.

## Step 1 — `shared/scripts/lib/sweep_gc.py`: canonical-form membership (AC-1, AC-2, AC-3)

**Current shape.** `parse_delivered(normalized_lines) -> (append_ids, text)` splits
origin's lines into the id-set of `event=="append"` entries and the raw text of
everything else. `is_delivered(stripped_line, append_ids, text)` mirrors that split.

**Target shape.** `parse_delivered(normalized_lines) -> (canonical, text)`:

- `canonical: set[str]` — `_canonical(obj)` for every line of origin that parses to a
  `dict`, regardless of `event`;
- `text: set[str]` — the raw stripped line of every origin line that does **not** parse
  (or does not parse to a `dict`).

`_canonical(obj)` = `json.dumps(obj, sort_keys=True, separators=(",", ":"),
ensure_ascii=False)`.

`is_delivered(stripped_line, delivered_canonical, delivered_text)`:

- parses to a `dict` → `_canonical(obj) in delivered_canonical`;
- otherwise → `stripped_line in delivered_text` (unchanged).

**Why the return arity stays 2.** The tuple keeps its shape, so the call site in
`sweep_outbox.py` needs no signature change — only the local variable names. Keeping
arity avoids touching the sweep's locked critical section in this run.

**Non-dict JSON.** A bare scalar (`"x"`, `3`) is valid JSON but not a record. Today it
lands in `text` via the `isinstance(obj, dict)` guard. Preserve that exactly — route it
to `text`, not `canonical`.

**Tests** (`shared/tests/test_sweep_gc_canonical.py`, new):

1. AC-1 — origin has append `{id:A, ts:T1}`; outbox line is `{id:A, ts:T2}` →
   `is_delivered` **False** (survives).
2. AC-2 — origin has status `{event:status,id:A,newStatus:dismissed}` serialized with
   one key order; outbox line has the other key order → **True** (dropped).
3. AC-3 — origin and outbox carry the same append, different key order + whitespace →
   **True** (FIX B's goal preserved).
4. Unparseable line present verbatim in origin → **True**; absent → **False**.
5. Bare scalar line routes through the text path, not the canonical path.
6. Empty/unreadable origin (`delivered_membership` returns `(set(), set())`) → nothing
   is delivered, i.e. every line survives (fail-safe preserved).

**Regression check.** Existing suites that pin the old two-set semantics:
`shared/tests/test_sweep_outbox.py`, `test_sweep_outbox_gc_reread.py`,
`test_sweep_outbox_review_cascade*.py`. Read them before editing; update only
assertions that encode the *id-only* rule, never ones that encode fail-safety.

## Step 2 — `shared/scripts/tools/triage_gc.py`: skip a damaged status event (AC-4)

In `_resolve_tracked_only`'s pass 2, replace

```python
new_status = raw.get("newStatus")
if new_status in triage.STATUSES:
    item["status"] = new_status
item["statusBy"] = raw.get("by")
item["statusReason"] = raw.get("reason")
```

with the guard `triage.py` already carries — `if new_status not in triage.STATUSES:
continue` — so `status`, `statusBy` and `statusReason` are either all applied or none.

**Why this matters beyond tidiness.** `is_machine_churn` keys its **delete** decision on
`statusBy` + `statusReason`. Under today's code a damaged event can overwrite both while
leaving a person's `status` in place, so a human decision can be reclassified as machine
churn and removed by `apply_gc` — which FR-01.14 forbids.

**Do not** also copy `triage.py`'s `item["ts"] = ...` assignment: that is a separate
behaviour this run does not own, and adding it would change GC ordering.

**Tests** (`shared/tests/test_triage_gc.py`, extend):

7. AC-4 — item dismissed by a person (`statusBy="cli"`, a human reason), then a status
   event with `newStatus="bogus"` carrying `by="driftProducer"`,
   `reason="driftResolved"` → all three fields unchanged, and `is_machine_churn` stays
   **False** so `plan_gc` does not schedule the deletion.

## Step 3 — drift protection for the twins (AC-5)

New test asserting `triage.read_all_items` and `triage_gc._resolve_tracked_only` agree
on the same damaged-status fixture: both leave `status`/`statusBy`/`statusReason` at the
prior decision. Placed in `shared/tests/test_triage_gc.py` so the resolver and its pin
live together.

This is the cheap substitute for extracting a shared overlay, which the operator
deliberately kept out of this run.

## Step 4 — `shared/scripts/lib/reconcile_triage.py`: comment correction (AC-6)

Rename the stale `_unrelated_staged` reference to `_has_staged_changes`, and state that
the guard is evaluated **outside** the lock, so it narrows the window rather than
closing it. Comment only — no behaviour change, no test.

## Revision after external plan review (2026-08-05, openai=revise / deepseek=approve)

Both reviewers ran; no contradiction. Every finding is addressed below, plus one the
review prompted me to find.

**R1 (openai, high) — duplicate JSON keys defeat canonicalization.** `json.loads` keeps
only the last of a duplicate key, so `{"id":"A","ts":"T1","ts":"T2"}` and
`{"id":"A","ts":"T2"}` produce the same canonical form — a materially different line
would be dropped, the exact class AC-1 exists to stop. **Accepted.** `_canonical` decodes
with an `object_pairs_hook` that rejects duplicate keys; such a line is
**non-canonicalizable** and falls back to raw-text membership (fail-safe: it survives
unless origin holds it byte-for-byte). Test: duplicate-key variants must not cross-match.

**R2 (openai, medium) — state the equivalence boundary.** **Accepted as documentation +
test.** The supported equivalence is exactly: object key order, insignificant whitespace,
and Unicode escaping. It is deliberately *not* numeric reformatting (`1` vs `1.0`
canonicalize differently). That direction is fail-safe — the line survives — and the
triage record schema carries no numeric fields, so it cannot arise from a real record.
Written into the `_canonical` docstring so the next reader does not re-derive it.

**R3 (openai, medium) — test the real caller, not only the pure helpers.** **Accepted.**
Add two end-to-end tests through `sweep_outbox_to_branch` with real git + real worktree +
the real lock: (a) a same-id content-changed append stays in the outbox; (b) a
canonically equivalent status line is dropped. The helper units stay.

**R4 (openai, low) + DeepSeek-1 (medium) — repo-wide reference search before shifting
semantics.** **Done, precondition confirmed.** The only production consumer is
`sweep_outbox.py`: it unpacks at `:246` and forwards both sets to `is_delivered` at
`:273`, with no direct membership test on the id set. Test references live only in
`test_sweep_outbox_review_cascade.py` and `test_store_git_timeout_paths.py` (the latter
asserts the `(set(), set())` fail-safe, which is unaffected). Locals renamed
`delivered_ids` → `delivered_canonical` so the call site reads true.

**R5 (openai, low) — canonicalization must not raise inside the lock.** **Accepted.**
`_canonical` is total: any `ValueError` / `RecursionError` / `TypeError` returns `None`,
and a `None` canonical form routes to raw-text membership. "Retain rather than drop" is
preserved for every input, which matters because this runs in the sweep's canonical lock
on the `setup_iterate_worktree` step-5 path.

**DeepSeek-2 (low) — drive each resolver the production way.** **Accepted.** The AC-5
drift test feeds `read_all_items` a real mini triage file and `_resolve_tracked_only` the
same file, comparing the resolved records — not a shared in-memory list.

**DeepSeek-4 (low) — the docstring still says `append_ids`.** **Accepted**, rewritten,
naming the id-only rule as the defect it was.

### R6 — found while checking R3/R4: two existing tests pin the defect

`test_sweep_outbox_review_cascade.py` proves "FIX B" with a fixture that **adds a key**
(`_append(..., extra=',"detail":"x"')`) and asserts the line **is** dropped — in
`test_gc_drops_delivered_append_even_if_reserialized` (end-to-end) and
`test_sweep_gc_membership_unit` (unit). An added key is not a re-serialization; it is
different content. So finding 14's loss is currently asserted as correct behaviour.

The module docstring states FIX B's real goal as *"re-serialized with a different key
order / whitespace"* — which those fixtures never exercise. Resolution:

- **correct the fixtures** to a genuine re-serialization (same key/value set, different
  order + whitespace) → still delivered, preserving FIX B and AC-3;
- **add the missing case** — same id, changed/added field → survives (AC-1).

This flips two `is True` assertions to `is False`. That is a fixture correction toward
the documented intent, **not** a weakening: no assertion is deleted or loosened, and the
behaviour FIX B claims to protect gains its first real test. Called out here, in the ADR
and in the review record so it is not mistaken for weakening a test to make a change pass.

## Verification

- `uv run pytest shared/tests/ -v` (one root per process — the repo `conftest.py`
  exits 4 on a mixed invocation). Run early, per DeepSeek-3, to surface any suite that
  implicitly depends on the old membership rule.
- `uvx ruff@0.15.15 check .` — hard CI gate.
- `uv run scripts/verify_local.py` — the three CI guards nothing else runs.

## Risks

1. **Widening the GC's drop set for status lines (AC-2).** New behaviour: a status line
   can now be dropped where it never could be. Bounded by exact canonical equality —
   origin provably holds the same record. The opposite direction (appends) gets
   strictly stricter.
2. **Existing tests may encode the id-only rule as intent.** Distinguish "pins FIX B's
   re-serialization immunity" (must keep passing, AC-3) from "pins id-only matching"
   (the defect). Do not weaken a test to make the change pass.
3. **`sweep_gc.py` runs inside the sweep's canonical lock and on the
   `setup_iterate_worktree` step-5 path.** `_canonical` must not raise: it is called on
   already-parsed `dict`s only, and `json.dumps` on a JSON-derived dict cannot fail.
   Keep it that way — no `default=` hook, no custom encoder.
