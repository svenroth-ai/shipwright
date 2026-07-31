# Mini-Plan — the compliance evidence documents ship at release

Companion to `2026-07-31-derived-docs-at-release.md`. Run
`iterate-2026-07-31-derived-docs-at-release`.

## Chosen approach — one producer, two deliveries

A single "recompute and verify" core, with the *delivery* as the only fork:

```
                    ┌─ regenerate to a fixpoint (converge)
   produce  ────────┼─ detect a FAILED pass (closed success vocabulary)
                    └─ content floor vs HEAD

   deliver ──┬── --stage   : write back → git add -- <the seven> → release commit
             ├── --pr      : take-the-set → branch → commit → push → gh pr create
             └── --restore : undo the release phase's SECOND, unstamped regen
```

The fork is real and belongs there. The release commit legitimately also carries
`CHANGELOG.md` and is reviewed by a human, so restore-to-base would destroy the
release's own edit. The on-demand commit must contain nothing else, so
take-the-set is exactly right for it.

### Files

| File | New? | Subject |
|---|---|---|
| `shared/scripts/lib/compliance_refresh.py` | new | Pure decisions: classification, the refresh set, convergence predicate, the floor rule, wording. No git, no IO. |
| `shared/scripts/tools/compliance_refresh_produce.py` | new | Recompute and verify: the converge loop, capture, the floor check, and every refusal. |
| `shared/scripts/tools/compliance_provenance.py` | new | What each document CLAIMS about itself: the fixed-point stamp, and `ci-security.json`'s scan provenance. |
| `shared/scripts/tools/compliance_delivery.py` | new | The git/index primitives, and the whole on-demand PR protocol (preflight, take-the-set, remote re-check, `gh`, cleanup). |
| `shared/scripts/tools/refresh_compliance_docs.py` | new | The CLI, the one-line release delivery, and `--restore`. |
| `shared/scripts/source_state.py` | edit | `base=` and `release=` tokens on the banner. |
| ~~`plugins/shipwright-compliance/scripts/lib/_provenance.py`~~ | **not edited** | The stamp moved to the DELIVERER (`stamp_fixed_point`): only it knows the fixed point, a renderer inside an ordinary iterate has neither a release nor a base, and this avoids a subprocess env-var boundary the external review would have been right to question. The compliance plugin is untouched by the stamp. |
| `plugins/shipwright-changelog/skills/changelog/SKILL.md` | edit | New Step 5.5, before the release commit. |
| `plugins/shipwright-compliance/skills/compliance/SKILL.md` | edit | Named step: open the docs-only PR. |
| `shared/scripts/tools/verifiers/derived_snapshot_gate.py` | edit | The remedy resolves the branch base. |
| `docs/guide.md`, `docs/hooks-and-pipeline.md` | edit | Item 4. |
| tests under `shared/tests/` | new | Per AC. All seven modules landed here: the subjects live in `shared/scripts/`, so `shared/tests` is their root. |

The `lib/` ⟷ `tools/` split mirrors `lib/churn_merge` ⟷
`tools/resolve_churn_conflicts`, the pattern the rest of the churn tooling
already uses: "which paths, and how does a refresh judge itself" is genuinely a
different subject from "how do I get them into a commit", and the split is what
lets the classification and the floor rule be tested without a git repository or
the compliance plugin on `sys.path`.

**Five modules, and the count moved three times — worth recording, because the
final answer is not the one I would have defended at the start.**

The first draft split `tools/` in two. External review (gemini) called that
over-production and was right about the *reason*: the seam I had drawn was a line
count. Collapsed to two. The single tool file then measured **491 lines**, so the
split came back — on the seam the diagram above already draws.

Then the review cascade landed 17 findings, and almost all of them were error
handling: a fail-open on a failed `git add`, a missing exception boundary, an
unreadable `ls-remote` read as reassurance, a rewind that ate concurrent appends.
Fixing them grew both files past 400. At that point two *subjects* had become
visible that were not visible at 250 lines:

- **what a document CLAIMS about itself** (the stamp, the scan provenance) is not
  the same subject as **how it was computed** → `compliance_provenance.py`;
- **the on-demand PR protocol** — its own preconditions, six failure states and
  its own cleanup obligation — is not the same subject as **the CLI and the
  one-line release delivery** → `compliance_delivery.py`.

So the count is five, and every seam is a subject. The honest summary is that the
right decomposition was not knowable before the error handling existed, and
gemini's objection was correct *about the draft it saw*.

## The alternative considered, and why not

**Regenerate inside `orchestrator update-step` and move that call before the
release commit.** It looks smaller — no new tool, one reordering.

Rejected on three counts:

1. `update-step --step changelog --status complete` runs
   `_validate_changelog()`, which now includes `check_git_tag_exists` and
   `check_changelog_version_matches_tag`. Moving it before the commit means
   validating a tag that does not exist yet. Chicken-and-egg.
2. It would give the *release* a fixpoint loop, a content floor and failure
   detection that no other phase has, buried inside a general-purpose
   orchestrator call. The verification belongs to the refresh, not to the
   phase-completion bookkeeping.
3. It has no answer at all for the on-demand PR (item 2), so item 2 would need
   the new tool regardless — and then the two paths would compute the documents
   two different ways. One producer, two deliveries is the whole point.

## Order of work

1. `lib/compliance_refresh.py` + its tests (classification, exclusions, AC-1/2).
2. `tools/compliance_refresh_produce.py` + tests (AC-3/4/5/6/9) — regenerate is
   injected, so the loop is testable without the compliance plugin.
3. `tools/refresh_compliance_docs.py` + tests (AC-7/8/8b/13).
4. `source_state.py` + `stamp_fixed_point` + tests (AC-9/9b).
5. `derived_snapshot_gate.py` + tests (AC-11/12) — separable, own files.
6. Skills + docs (AC-10).

## Risk

No risk flags fire: nothing under `.github/workflows/**`, no `hooks.json`, no
`*_config.json` / `*_state.json`, and none of the `cross_component` machinery
(`integrate_main`, `ensure_current`, `resolve_churn_conflicts`, `churn_merge`,
hooks, phase validators, campaign drain). `regenerate_tracked_snapshots` is
*called* but not edited — deliberately, because editing it would pull
`resolve_churn_conflicts.py` into the diff and with it the `cross_component`
integration-coverage requirement.

The real risk is the opposite of a gate: a refresh that runs, reports green and
ships an emptied document. That is what AC-4 and AC-5 exist for, and both are
ported rather than invented because the parked branch already found the exact
failure modes the hard way.
