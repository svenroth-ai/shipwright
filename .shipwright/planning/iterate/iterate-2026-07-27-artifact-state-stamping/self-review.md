# Self-Review — iterate-2026-07-27-artifact-state-stamping

The 7-point checklist. Pass/fail + one sentence each. Run before F0.

**1. Spec Compliance — PASS.** AC1–AC9 all implemented and each pinned by a named test;
nothing beyond the card's scope was added (no gate, no third producer, no schedule for the
cross-check), and the two sibling cards' files were left alone apart from the one
deliberate, documented reach into the test plugin's write path.

**2. Error Handling — PASS.** Every external boundary degrades instead of raising: `git`
missing/timeout/non-repo/empty-repo → `None`; a corrupt or non-object record → exit 1 with
*nothing written*; a corrupt run config → still stamps what is resolvable; `from_block`
is total over arbitrary input. The one place a hard failure is correct — an unreadable
record — is a refusal, not an overwrite.

**3. Security Basics — PASS (after two fixes).** Values reaching a rendered artifact are
treated as untrusted: `safe_run_id` refuses whitespace, Unicode control/format/separator
characters and unsubstituted `{}` placeholders; `safe_commit` refuses anything that is not
7–40 hex. Both were *added in response to review* — the first implementation interpolated
`commit` unvalidated, which allowed a forged status token and a second banner line. `git`
runs with an argument array, `shell=False`, and a bounded timeout. No secrets, no user
input reaching a shell or a query.

**4. Test Quality — PASS.** 71 + 39 + 60 cases assert on observable outputs (rendered
document text, the JSON on disk, exit codes) rather than internals. Three assertions that
could not fail on their advertised property were found by the doubt reviewer and
strengthened; the canonical-form test now asserts on **bytes** so a CRLF regression can
actually fail it. Every bug found during this iterate — the `dirty` three-state collapse,
the `clean` substring collision, the commit forgery, the run-id fallback — has a named
regression test.

**5. Performance Basics — PASS.** Two short-lived `git` calls per stamp (`rev-parse`,
`status`), both bounded at 10s. The renderers gained one string per document. No loops
over I/O, no unbounded reads.

**6. Naming & Structure — PARTIAL, disclosed.** Naming and placement follow existing
convention (`shared/scripts/` for cross-plugin helpers per ADR-045; `_provenance.py`
alongside the other `_`-prefixed compliance leaves; `stamp_test_results.py` mirroring
`record_coverage_total.py`). **Two files exceed the 300-line guideline**:
`shared/scripts/source_state.py` at ~340 and `collectors/_types.py` at 302. The first is
new and coherent (one model, two serializations, one resolver) and was already trimmed
twice; the second is the pure-dataclass file that was *already at exactly 300*, so the one
field this change requires cannot be added without crossing. Neither is in the
anti-ratchet baseline, so both are new crossings — nudge-only, surfaced by the Group H
audit post-merge. Recorded rather than silently accepted.

**7. Affected Boundaries — PASS.** Two producer/consumer pairs identified in the spec and
both proven by a real round-trip (producer → file on disk → consumer), not by inspection.
The diff-driven `touches_io_boundary` flag does **not** fire — it matches file paths and
this diff is `.py`-only — so the Boundary Probe was run **voluntarily**, including all
five applicable categories of the 8-category list (BOM, CRLF, non-ASCII, `#`-in-value,
empty/whitespace values); the three env-file-specific categories are justified-skipped
because neither format is an env file. The absence of the flag is disclosed in the spec so
it is not mistaken for "no boundary was touched".

## What this review itself caught

Not delegated findings — these came from re-reading my own diff:

- **`dirty=False` and `dirty=None` rendered identically**, collapsing "clean tree" into
  "git could not answer". That is the exact honesty distinction the whole change exists to
  make, so the banner now carries three states and the round-trip test pins all three.
- **`_CLEAN_TOKEN in line` was a substring test.** A run id ending `-cleanup` — and
  SIMPLIFY-mode runs are named precisely that — would have parsed an unresolved `dirty`
  back as a confident `False`. Now matched as an exact whitespace-delimited token.

## Honest note on the review sequence

The external code review's two highest findings ("the tool is wired to nothing", "no tests
exist") were **artifacts of my own diff narrowing** — I had excluded the wiring and test
files to get under the reviewer's output limit after a first attempt came back truncated
(29 and 504 characters). The findings were correct about the slice they saw and wrong about
the change. The lesson is recorded because the same narrowing could have hidden a real
gap: a review of a subset must be labelled as one.
