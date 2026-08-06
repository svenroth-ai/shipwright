# Mini-Plan — Adopted repos: honest evidence, and a remedy that works

Run: `iterate-2026-08-05-adopt-derived-evidence-rollout` · medium · CHANGE

---

## The shape

Three independent slices. None depends on another, so review can split them if the
cascade gets noisy.

### Slice 1 — Onboarding stamps what it seeds (AC-1, AC-2, AC-3)

**A fifth mode on `shared/scripts/tools/refresh_compliance_docs.py`**, whose
substance lives in a new sibling `shared/scripts/tools/compliance_adopt_stamp.py`.

> **Deviation from the approved plan, recorded at build time.** The plan put the
> mode's body in `refresh_compliance_docs.py` itself, arguing (correctly) that
> there is no bloat baseline entry to ratchet. Writing it took the file to **318
> lines**, past the 300-line guideline — a *new* crossing, which the Group H
> detective audit surfaces post-merge even though the pre-commit anti-ratchet
> would not have blocked it. So the R2 reasoning was right about the hook and
> incomplete about the guideline.
>
> The split is not merely a line-count dodge: that file's own docstring says the
> substance lives in siblings — `compliance_refresh_produce` (recompute/verify),
> `compliance_delivery` (the PR protocol), `lib.compliance_refresh` (which paths
> and why) — and it stays a thin deliverer plus CLI. An 80-line delivery body
> inline broke that pattern as much as the cap. After the split:
> `refresh_compliance_docs.py` **253**, `compliance_adopt_stamp.py` **113**.

```
--stamp-adopted --project-root <root> [--base <sha>]
```

1. Resolve the base — **three-way, and a fallback is not the default branch**
   (openai R2, medium; AC-2):
   - `--base` **given and resolving** → use it. Adopt passes the `adopted` event's
     `commit_at_adoption`, the authoritative record of the commit onboarding read.
     Accept only a canonical commit object: `safe_commit` for the lexical check
     **plus** `git rev-parse --verify <sha>^{commit}` in the target root, so a
     symbolic revision cannot become misleading provenance (openai R2, low).
   - The banner carries **the full commit ID `git rev-parse --verify` returned**,
     not the string that was passed in. `safe_commit` accepts an abbreviated SHA,
     and stamping the input rather than the resolved object would weaken the
     canonical-provenance claim the validation exists to make (openai R3, low).
   - `--base` **absent, malformed, literal `"HEAD"`, or not resolving to a commit
     in this repository** → `no_base`, in every one of those cases.
     **`--stamp-adopted` never resolves `HEAD` on its own.**

   The last point is a correction of this plan's own earlier draft, which let an
   *absent* `--base` fall back to `HEAD` while refusing the fallback for a
   *malformed* one. That asymmetry had no justification: both mean the
   authoritative value could not be established, and resolving `HEAD` in either
   case reintroduces exactly the timing failure the recorded value was adopted to
   remove (openai R3, high). The generic `HEAD` default belongs to `--stage` and
   `--pr`, which describe *now*; this mode describes *when onboarding read the
   repository*, and only the caller knows that. An absent `--base` here is a
   caller bug, and is reported as one.

   *(Both reviewers, R1 high/medium: deriving the base from `HEAD` at Step H is an
   unstated timing invariant — it holds only if nothing commits between seeding
   and stamping, which resume, retry and operator intervention all break. The
   recorded value has no such assumption. See the correction note below.)*
2. Build the payload from **the `.md` members of `REFRESH_SET`**, not from
   `COMPLIANCE_MDS` directly, with a runtime invariant asserting the two agree
   before writing. Correctness is defined in terms of `REFRESH_SET`; consuming a
   second list means production code can stamp a divergent set until the drift
   test next runs (openai R2, medium). Probed: the filter yields exactly five.
3. `tools.compliance_provenance.stamp_fixed_point(payload, base_sha, release=None)`
   — **in memory.** Nothing is on disk yet.
4. **Validate completeness BEFORE writing.** Compare the returned `stamped` list
   against the expected set. Only on a complete stamp (or the intentional
   `no_base`) does step 5 run.
5. `tools.compliance_git.write_back(root, payload)` — signature probed as
   `(root, payload: dict[str, bytes])`, so it composes with step 3's return
   directly.
6. Print `{"status": ..., "base": ..., "stamped": [...], "expected": 5}`.

**Validate-then-write, not write-then-validate** (openai R3, medium). An earlier
draft of this list wrote first and compared after, so a partial stamp aborted
adoption *having already mutated the repository* — no bad commit, but a dirty
tree that then fouls retry, the clean-tree preconditions elsewhere in this same
change, and an operator's recovery. Building the payload in memory makes the
failure non-mutating.

No new stamping logic — every step reuses #512. `release` is `None` by
construction; **probed 2026-08-06**, `stamp_fixed_point` rewrites the whole banner
line, so a pre-existing `release=v0.4.0` is *removed* rather than merely not added
— AC-3 holds structurally. A regression test pins it.

**A shortfall is FATAL, not a printed note.** Probed: `stamp_fixed_point` leaves a
document with no `Source-State:` line **untouched** and simply omits it from its
return list. So the mode compares `stamped` against the expected set and, on any
shortfall, returns `status: "partial"` **and exits non-zero**. A JSON status with
exit 0 is trivially ignored by a subprocess wrapper, and the result would be an
adoption commit carrying a half-stamped evidence set — the same "reported stamped,
shipped unstamped" shape #512 was bitten by (openai R2, high).

**Step H's contract:** proceed to the commit only on a complete stamp or the
explicit `no_base`. Anything else aborts adoption **before** committing, so a
partial stamp produces no commit at all rather than a bad one.

**One deliberate difference from the other modes: this one is non-fatal when no
base resolves.** `--stage` and `--pr` must refuse hard — shipping unstamped
evidence is the failure they exist to prevent. But a repository with no commits
yet is a legitimate onboarding case (`event_seeder.py:75` even carries a literal
`"HEAD"` fallback for it), and refusing there would block adoption over a banner
field. So it reports `status: "no_base"`, writes no `base=`, leaves the rest of
the banner untouched and exits 0. That **is** AC-2, and the difference is stated
here so a later reader does not "fix" it into a refusal.

**Adopt invokes it as a subprocess, never by import.** `seed_adopt_compliance.py`
already puts adopt's own `scripts/lib` on `sys.path` as `lib`, so an in-process
import of a module doing `from lib.compliance_refresh import ...` would bind the
wrong `lib` (ADR-045). Subprocess is the existing pattern there
(`run_update_compliance`).

**Where it is called — Step H, immediately before the commit.** Not Step F.
Between F and H sits Step G (Layer-3 review), and any phase-completion
regeneration in that window would overwrite the stamp with an unstamped render.
That is exactly the false green #512 hit ("the stamp never reaching the release
path while the run reported `stamped: [...]`"), so the window is closed rather
than assumed empty.

**And verified after the commit.** Step H then runs the already-built
`refresh_compliance_docs.py --verify-commit <sha>`, which reads the blobs out of
the commit rather than the worktree — `git commit -- <paths>` records the working
tree, so nothing else proves what shipped.

**Verification is skipped when the stamp reported `no_base`.** Confirmed in code:
`verify_commit` appends to `missing` when `state is None or not state.base` and
returns exit 1, so on a repository with no commits it would reject a commit that
is correct by AC-2 and fail a legitimate onboarding (deepseek, medium). Step H
therefore branches on the stamp's own reported status rather than verifying
unconditionally.

**On mismatch: one re-stamp and amend, then verify the amended commit, then stop.**
The amend is path-limited to the five compliance paths — it must not sweep up
unrelated operator changes — and is attempted **once**. The amended SHA is then
run back through `--verify-commit`; without that the amend can report success
while a hook or concurrent writer has changed a compliance file again (openai R2,
medium). A second mismatch reports the differing paths and stops, rather than
rewriting the adoption commit indefinitely whenever the cause is deterministic.

### Slice 2 — Say it, twice (AC-4, AC-5)

- `references/step-h-validate-commit-handoff.md` — one banner line
  (`Evidence:  current as of this commit; refreshed at releases and on demand`)
  and one next-step bullet naming `/shipwright-changelog` and
  `/shipwright-compliance --refresh-pr`.
- `claude_md_renderer.py` — replace the bare "Compliance + dashboard refresh"
  line with the same statement, so the fact outlives the banner.

### Slice 3 — A remedy that can clear the finding (AC-6)

`group_e.py:_suggest()` currently returns `--fix` alone. It becomes both paths,
because they clear different cases and only one of them is ever right:

- `--fix` — the on-disk copy drifted from the committed snapshot (hand-edit,
  partial regen). Re-rendering restores it.
- `--refresh-pr` — the committed snapshot is genuinely behind. Re-rendering
  cannot clear this; only a new snapshot commit can.

**And it must be an ORDERED path, because `--refresh-pr` alone would refuse.**
`preflight_pr` requires a clean tree — and a Group E finding *means* the on-disk
document differs from its committed snapshot, so at the moment the remedy is
offered the tree is dirty in exactly those files. Naming `--refresh-pr` on its own
sends the operator straight into `"the working tree has uncommitted changes"`
(openai R2, high). The compliance skill already documents the resolution in Step
2c — **`--restore` first, then `--refresh-pr`** — so the suggestion names that
order rather than inventing a new one. Verified against `preflight_pr` in an
integration test, not by asserting the suggestion string.

**And it says that restoring the evidence files is not sufficient on its own.**
`--restore` resets only the seven; `preflight_pr` refuses on *any* uncommitted
change, and running an audit with unrelated edits in the tree is a normal
operator state, not an exotic one. So the wording states that unrelated changes
must be committed or stashed too — otherwise the remedy reads as a guarantee it
cannot make (openai R3, medium).

**It stays ONE string.** `_suggest` keeps returning a single value carrying both
options with the condition attached, rather than a list or two findings — the
finding text is consumed by the WebUI's finding list and by report rendering, and
a shape change there is a separate blast radius this iterate has no reason to take
(both reviewers, low). The consumer contract is checked before the wording lands.

## Docs (same diff, per the CLAUDE.md rules)

- `docs/guide.md` — the adopt chapter gains the pointer to §10's "How current are
  these documents?", which already carries the full explanation.
- `docs/hooks-and-pipeline.md` — artifact-write matrix: adopt now writes the
  provenance stamp and verifies the commit.

## Tests

One root per pytest process (ADR-044) — three invocations.

| Root | Test | Covers |
|---|---|---|
| `shared/tests` | `test_refresh_compliance_docs.py` (extend — it already covers the sibling modes) | **absent / malformed / literal `HEAD` / non-resolving `--base` all yield `no_base`, and `HEAD` is never resolved by this mode**; an abbreviated `--base` is stamped as the **full resolved** commit ID; a pre-existing `release=` is **removed**; a banner-less document yields `partial`, a **non-zero exit**, and **an unchanged worktree**; **round-trip** `stamp_fixed_point → parse_banner_line` (Boundary Probe) |
| `shared/tests` | set-agreement test + runtime invariant | the stamped set is exactly the `.md` members of `REFRESH_SET` — pins the seven-vs-five mapping (below) so it cannot read as an oversight |
| `integration-tests` | adoption-commit integration test | **the ordering guarantee**: in a temp git repo, run the Step F→H path and assert the resulting *commit's blobs* carry the stamp; plus the verification-mismatch → amend → re-verify branch (openai R1, medium — a unit test of the mode alone cannot catch a reordering that reintroduces the unstamped-commit regression) |
| `integration-tests` | partial-stamp abort test | a banner-less expected file **aborts adoption, produces no commit, and leaves worktree + index unchanged** (openai R2 high, R3 medium) |
| `integration-tests` | Group E remedy with unrelated dirt | an unrelated uncommitted file still blocks `--refresh-pr` after `--restore` — so the finding text never implies restoring the evidence alone is enough (openai R3, medium) |
| `integration-tests` | empty-repo onboarding test | a repo with no commits and a literal `HEAD` in the event: onboarding completes, its first commit succeeds, the evidence carries no `base=`, and verification is skipped rather than counted as a failure (openai R2, medium) |
| `integration-tests` | Group E remedy executability | the suggested `--restore` → `--refresh-pr` order actually passes `preflight_pr` from the state Group E reports — the finding's remedy is run, not string-matched (openai R2, high) |
| `plugins/shipwright-adopt/tests` | prose drift test (precedent: `test_skill_md_env_scaffold.py`) | AC-4 |
| `plugins/shipwright-adopt/tests` | `test_claude_md_renderer` addition | AC-5 |
| `plugins/shipwright-compliance/tests` | `_suggest` test | AC-6, incl. that it stays a single string |

### Seven documents, five stamped — not a gap

Both the card and #512 speak of "the seven". `REFRESH_SET` is five markdown
documents plus `test-traceability.json` and `ci-security.json`. Only the five
markdown ones carry a `Source-State:` banner at all — `stamp_fixed_point` skips
non-`.md` members deliberately (`ci-security.json` states its provenance in its
own `source`/`scan_date` fields, and `test-traceability.json` has a schema with
contract tests that is not this change's to extend). So stamping five **is**
stamping the whole set, and the set-agreement test above pins it (openai, medium).

Expected risk flag: `touches_io_boundary` (a new writer joins the banner
producer/consumer pair) → Boundary Probe + round-trip test, both above.

## Alternative considered — a separate `stamp_adopted_evidence.py`

A new ~70-line single-purpose tool in `shared/scripts/tools/`, resolving the base
by reading `commit_at_adoption` out of the `adopted` event.

**This was the original recommendation and it was withdrawn, because both
arguments for it turned out to be false.** Recorded rather than quietly swapped,
since the same two arguments will occur to the next reader:

- *"Every existing mode runs `produce()`, so a stamp-only mode would be the odd
  one out."* **False.** `--verify-commit` returns at `refresh_compliance_docs.py:153`
  and `--restore` at `:165`, both before `produce()`. Two of the four modes
  already skip it; a fifth that also skips it fits the file's existing shape.
- *"It is 232 lines with a bloat baseline entry, so a fifth mode ratchets it."*
  **False.** `shipwright_bloat_baseline.json` has 188 entries including many
  `shared/scripts/tools/*` paths, and `refresh_compliance_docs.py` is not among
  them — it is under the 300-line limit, so there is no entry to ratchet.

With those gone, the fifth mode is better on the merits: Step H **already** has to
call this exact tool for `--verify-commit`, so adopt invokes one tool twice
instead of two tools once each.

**One thing that switch got wrong, and the external review caught.** Moving to the
fifth mode, the base source was also changed from the recorded
`commit_at_adoption` to a `HEAD` read at stamp time — treated as a free
simplification because at Step H the two are equal. They are equal only under an
unstated timing invariant that resume, retry and operator intervention all break,
and both reviewers flagged it independently (openai high, deepseek medium). The
two decisions were never coupled: **the fifth mode stands, the base comes from the
recorded value**, with `HEAD` as fallback only. Recorded because the same
"simplification" is available to the next reader.

**Shared dependency, stated so a refactor notices it** (deepseek, low): this mode
depends on `tools.compliance_provenance.stamp_fixed_point` and
`tools.compliance_git.write_back` exactly as `--stage` and `--pr` do. Moving
either breaks four modes, not two.

## Rejected outright

- **Teaching the ordinary producer to carry `base=`.** It would churn every
  tracked document on every commit, reintroducing what
  `iterate-2026-05-22-deterministic-render-timestamps` removed. Reasoning in the
  spec.
- **Any post-merge producer (Weg A).** Rejected 2026-07-30 by three reviews.
- **A customer-side precondition check** (ruleset, credential, bypass actor).
  There is none to check; `preflight_pr` already refuses clearly and in plain
  words when `gh`, the remote or the tree is not ready.
