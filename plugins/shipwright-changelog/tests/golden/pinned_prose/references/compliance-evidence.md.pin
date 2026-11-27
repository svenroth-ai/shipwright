# The compliance evidence documents at release

Reference for **Step 5.5** and **Step 8** of `/shipwright-changelog`.
Background: `.shipwright/planning/iterate/2026-07-30-derived-snapshots-decision.md`.

## What ships, and why here

Seven documents live under `.shipwright/compliance/`: `dashboard.md`, `sbom.md`,
`test-evidence.md`, `traceability-matrix.md`, `change-history.md`,
`test-traceability.json`, `ci-security.json`.

They are **derived** — every line is recomputable from `shipwright_events.jsonl`,
`.shipwright/triage.jsonl` and git history, all of which already ship. They carry
no information of their own.

An iterate branch must not commit them, and `check_no_derived_snapshots_committed`
enforces it. The reason is measured, not stylistic: a branch-local derivation
reads the *branch's* git history and an event log missing every concurrently
merging branch. On 2026-07-27 the default branch's committed `change-history.md`
over-counted commits by 11 and cited a SHA `git merge-base --is-ancestor` proves
was never on it. Twenty-five parallel branches also all rewrite the same seven
files regardless of what they changed, which generates conflicts in series.

PR #480 stopped that, and the documents have stood frozen since. **The release is
where the objection disappears**: one branch, one human, one reviewed pull
request. So the release checks them in.

They are already recomputed today — `PHASE_REPORTS["changelog"]` in
`update_compliance.py` covers every one of them. That call just happens in Step 8,
*after* the release commit, so the fresh copies land in the working tree and are
never staged. Step 5.5 is that same computation, moved to where it can ship.

## Why `.shipwright/planning/adr/` is staged, and as a directory

Step 4's `aggregate_decisions.py` refreshes `.shipwright/planning/adr/INDEX.md` on
**every** non-dry-run pass — including one that folds zero drops — so a release
can repair an index that had gone stale. Leaving that unstaged makes the local
drift guard pass against a repaired working tree while CI fails against the
committed one. A folder-level add is a no-op when nothing changed.

It is a *directory* pathspec on purpose, unlike the evidence paths: its contents
are release output whose file names are not known in advance, whereas the seven
are a pinned set that a directory pathspec would silently widen.

## Why `decision_log_index.md` is staged as its own file, every pass

Same reasoning, one file instead of a directory. `aggregate_decisions.py` refreshes
`.shipwright/agent_docs/decision_log_index.md` on every non-dry-run pass too —
it is a pure function of `decision_log.md`'s own (possibly just-folded) content,
so whichever of that file or the log itself changed, the index can too. Leaving
it unstaged commits the log while the index sits at old bytes: the local drift
guard (a repaired working tree) passes while CI (the committed tree)
fails — `test_decision_log_index_producers.py::test_committed_index_is_not_stale`.
It is a single pinned filename, not a directory, because — unlike the ADR
folder — a release never mints an unpredictable new filename for it.

## Reading the tool's output

`status: "ok"` — proceed. `staged` lists what actually differed from `HEAD`, and
`commit_pathspec` is the exact pathspec Step 6 must use.

`status: "producer_failed" | "not_converged" | "content_floor"` — **stop and
investigate; do not tag.** The tool has already restored the tree and put the
index of the seven back as it found it (`unstaged` names the paths; before P8b,
F8, what the producers had staged stayed staged), so nothing
untrusted is left lying around. Each refusal exists because a refresh that reports
green while shipping frozen or emptied documents is worse than one that stays
frozen:

| status | what happened |
|---|---|
| `producer_failed` | a generator leg did not report success. It writes nothing when it fails, so the output is unchanged, so it *converges immediately* — which is exactly why the outcomes are checked before the convergence verdict. |
| `not_converged` | four passes did not agree. `update_compliance` collects once and renders in list order, so the RTM reads the `test-traceability.json` the same pass later overwrites; two passes normally settle it. A producer that stops settling must fail loudly rather than have whichever pass ran last committed. |
| `content_floor` | a document lost material content against `HEAD`. `collect_git_history` returns `[]` on its 30-second timeout and renders a well-formed document with no rows — which converges perfectly. |

`--allow-shrink` waives the ratio floor (not the empty floor) for a legitimate
large removal. The output's `allow_shrink.waived` **names the documents it
actually covered** — an empty list means the flag was passed and never mattered,
which is a different fact from a document having halved.

## `ci-security.json` is not like the other six

It derives from the **latest completed CI scan**, not from the repository. At
release time that is fine in practice — a scan has just run on the release PR —
but its freshness is not a property of the commit, so it is excluded from the
fixpoint claim and reported separately:

- `stale: true` — the committed scan predates the base commit; it describes older
  code. Report it in the release notes if it matters.
- `stale: null` — one side had no date, so the comparison did not happen. Not the
  same as fresh.

**It never blocks a release.** A release is not held for a scan that has not
landed.

## The stamp

Each markdown document's `Source-State:` banner gains `base=<commit>` and
`release=<tag>`, so the evidence names a fixed point rather than implying it is
live. For audit evidence a fixed point is the better claim anyway.

`--release` is **passed in** and never read from git — at Step 5.5 the tag does
not exist yet. The two `.json` members carry no banner: `ci-security.json` states
its own provenance in `source` / `scan_date`, and `test-traceability.json` has a
schema with contract tests.

## Why the tree ends clean

Step 5.5 writes the seven documents once and Step 6 commits them (stamped, by explicit pathspec). The derived snapshots are never committed
otherwise (`shared/scripts/lib/derived_snapshots.py`, `DERIVED_SNAPSHOTS`), and any producer that rewrites one after that commit leaves a tree
that disagrees with what was committed. A hand-invoked release must not end that way, so `release.py close-phase` runs
`restore_derived_to_head` (through `checks/restore_derived.py`): the committed copies win and the tree ends clean. It is a no-op when nothing was
rewritten, so no path needs to know which producer ran. A driven run keeps its canon records (the master's gate reads them) and restores nothing.

## Between releases

`/shipwright-compliance --refresh-pr` opens a documents-only pull request from the
same producer. Same checks, same visibility, the operator's own GitHub login — no
bot, no key, no exception to the branch-protection rule.
