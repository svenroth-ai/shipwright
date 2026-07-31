# External plan review — `iterate-2026-07-31-derived-docs-at-release`

Providers: `gemini`, `openai` (via openrouter). Both verdicts: **revise**.
No contradiction. Raw payload: `external-plan-review.raw.md`.

Every finding below is dispositioned. Nothing is deferred silently.

---

## Accepted and folded into the build

### O1 (high, dependency) — the post-release regen rewrites what was just committed

**Finding.** The changelog skill's Step 8 runs `orchestrator update-step --step
changelog --status complete`, which calls `run_compliance_update(root,
"changelog")` — regenerating all seven documents **after** the release commit.
The regenerated copies carry no `base=`/`release=` tokens (those come from
environment set only in Step 5.5) and are computed at a different commit, so the
worktree is left permanently dirty against what was just committed. That is the
dirty-worktree/order defect this change exists to remove, reintroduced one step
later.

**Verified before accepting.** `PHASE_REPORTS["changelog"]` in
`update_compliance.py` names `rtm, test_evidence, test_links, change_history,
sbom, dashboard` — the whole set. The finding is correct.

**Resolution.** `refresh_compliance_docs.py` gains a `--restore` mode that resets
exactly the seven paths to `HEAD`, and the changelog skill runs it as the last
action of Step 8. The committed, stamped copies win; the second regeneration's
output is discarded, which is what the existing `restore_derived_to_head` already
does for the same reason in the iterate flow. AC-13.

### O2 (high, edge-case) — `release=` has no meaning for the docs-only PR

**Finding.** A docs-only branch off `origin/main` is not associated with any
release. Stamping the latest tag would claim the documents "shipped with" a
release they did not ship with; omitting it silently gives one producer two
semantics.

**Resolution.** `release=` is emitted **only** by the release delivery. `--pr`
and `--release` are mutually exclusive at the CLI and the tool refuses the
combination rather than picking one. The docs-only PR stamps `base=` alone,
which is the whole truth about it. AC-9b.

### O3 (high, risk) — staging seven paths does not bound the release commit

**Finding.** `git add -- <seven>` is additive. Anything an earlier step or the
operator already staged rides the eventual `git commit`.

**Resolution.** The boundary moves from the index to the commit, matching the
take-the-set reasoning the parked branch already established: the release commit
is made **by explicit pathspec** — `git commit -m … -- CHANGELOG.md <the
seven>` — so it contains exactly those paths whatever else the index holds. The
tool prints the exact pathspec for the skill to use verbatim. AC-7 restated.

### O4 (medium, edge-case) — a stale CI scan is not visible on `main`

**Finding.** AC-6 as written reports the frozen state in *tool output*, which is
not durable evidence. A reader of `main` sees only the document.

**Partially accepted.** The document is not silent: `ci-security.json` carries
its own `source` (`security.yml#<run_id>`) and `scan_date` fields, which are
durable and committed. What was genuinely missing is the relation the reviewer
names — no acceptable-age rule, so a very old successful scan reads as current.

**Resolution.** The tool compares the committed `scan_date` against the base
commit's date and reports `ci_security.stale: true` with both dates when the scan
predates the code it is being shipped alongside. It stays **non-blocking** — the
operator's decision is explicit that a release is never held for a scan that has
not landed. AC-6 extended.

### O5 (medium, edge-case) — `main` can advance between fetch and PR creation

**Accepted in the cheap direction.** The stamp stays honest either way — `base=`
names what was actually computed from, which remains true. But recomputing is
cheap and shipping a knowingly-stale refresh is pointless, so the tool re-reads
`origin`'s default-branch SHA immediately before pushing and aborts with a clear
message if it moved. AC-8b.

### O7 (low, security) — argv arrays and ref validation

**Accepted.** Every `git`/`gh` call uses an argument list, never a shell string.
`base` is validated with `source_state.safe_commit` (7–40 hex) and `release` with
the same single-token rule `safe_run_id` applies, **before** either reaches a
banner or a ref name. A value that fails validation is dropped, not sanitised
into something that looks legitimate.

### G2 (medium, edge-case) — the content floor blocks legitimate shrinkage

**Accepted.** A large removal can legitimately halve a document. The floor stays
on by default and gains `--allow-shrink`, which records the override and the
paths it covered in the tool's output. Explicit, never silent. AC-5 extended.

### G1 (high, reducibility) — three files is over-production

**Partially accepted.** Splitting `tools/` in two was thin — the seam was a line
count, not a subject. Collapsed to **two** files: `lib/compliance_refresh.py`
(pure decisions, no git/IO, unit-testable without the compliance plugin) and
`tools/refresh_compliance_docs.py` (everything that touches the world).

The `lib` ⟷ `tools` split itself is kept and is not over-production: it is the
established pattern for exactly this subject in this repo (`lib/churn_merge` ⟷
`tools/resolve_churn_conflicts`, `lib/derived_snapshots`), and it is what lets
the classification and the floor rule be tested without a git repository or the
compliance plugin on `sys.path`.

---

## Answered, no change

### G3 (medium) — the release tag does not exist yet at Step 5.5

**Already the design, now stated.** The version is passed as `--release
v{version}` by the changelog skill, which knows it from Step 3. Nothing reads
`git describe` or any tag. Made explicit in the spec and pinned by a test that
the tool never shells out to resolve a tag.

### G4 / O-tail (low) — is the on-demand command local or CI?

**Local only.** It runs on an operator's machine under their own `gh` login.
There is no workflow, no PAT, no `GITHUB_TOKEN`, and nothing is added to
`.github/`. That is the entire point of Weg B: no credential with write access to
`main` exists to be secured or rotated. Stated in the docs.

### O6 (medium) — do not duplicate the snapshot registry

**Already satisfied.** `CLASSIFICATION` is keyed off `DERIVED_SNAPSHOTS`,
`COMPLIANCE_MDS`, `TEST_TRACEABILITY`, `CI_SECURITY_SUMMARY` and `TEST_RESULTS`
imported from `lib/churn_merge` and `lib/derived_snapshots` — there is no second
inventory. `unclassified()` fails closed on any registry member without a class,
which is the protection the reviewer asks for.
