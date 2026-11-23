# Re-running a release

Referenced from SKILL.md Step 4. Covers what happens when
`aggregate_changelog.py` is run for a version that is already in
`CHANGELOG.md` — the normal consequence of a release that stopped partway.

## Why a re-run happens at all

The aggregator writes `CHANGELOG.md` **before** it deletes the drop files it
consumed. There is no way to make those two steps one atomic act, so an
interruption in that window is a real state: the section is written *and* every
drop is still pending. The operator's instinct — run it again — used to insert
a second `## [x.y.z]`.

## What a re-run does

| State on disk | Action | `section_action` |
|---|---|---|
| no drops pending | nothing; the changelog is not even read | `none` |
| no section for this version | insert it | `inserted` |
| one section, and it says what the drops say | rewrite it in place, then consume the drops | `replaced`, or `unchanged` when the bytes were already right |
| one section, and it does **not** say that | **refuse** | — (non-zero exit) |
| one section carrying a marking a re-render would erase | **refuse** | — (non-zero exit) |
| more than one section for this version | **refuse** | — (non-zero exit) |

## Why it refuses instead of just overwriting

Deleting the drop files is not atomic either. If a run consumed some of them
and then died, the section on record holds *more* bullets than the surviving
drops would render. Overwriting it would delete released history — strictly
worse than the duplicate section this whole mechanism exists to prevent, since
a duplicate loses nothing.

So the aggregator replaces only when replacing cannot lose anything: when the
recorded body is what the pending entries now say, and the recorded heading
carries nothing beyond a version and a date. Anything else stops and names the
disagreement.

A refusal changes **nothing** — not `CHANGELOG.md`, not a single drop file. It
is a prompt to reconcile the two by hand, not a transient error to retry.

## Dates

`--release-date` defaults to today, and the comparison deliberately ignores the
date so a release resumed the next morning still converges. A replace adopts
the newly rendered heading, so pass `--release-date` explicitly when the
original date matters.

A heading carrying more than a version and a date —
`## [1.2.0] - 2026-04-23 [YANKED]` — is refused rather than silently rewritten,
because a replace rewrites the whole heading line and the marking would be lost.

## Reading the result

`changelog_updated` means **bytes were written**, not *the run succeeded*. A
converging re-run reports:

```json
{ "section_action": "unchanged", "changelog_updated": false }
```

That is a **success** — the file was already exactly right and the drops were
still consumed. Likewise `"section_action": "none"` means there was nothing
pending. Neither is a reason to retry or escalate. A genuine failure is a
non-zero exit with the reason on stderr.
