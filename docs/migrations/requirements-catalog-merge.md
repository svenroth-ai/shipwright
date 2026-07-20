# Migration — one requirements catalog

**Applies to:** projects using `/shipwright-project`, `/shipwright-adopt` or
`/shipwright-compliance`.
**Introduced by:** the requirements-catalog campaign, step S6.
**Do you have to do anything?** Check two things before upgrading — either can
turn a passing audit red:

1. **Do several requirement documents reuse the same ID numbers?** Duplicate-ID
   detection is now global instead of per document.
2. **Can your requirements table actually be read, while your change log names
   requirements?** If the answer is "no" and "yes" together, the audit now fails
   where it previously said nothing.

If neither applies, no action. Both are explained below, with the fix.

## What changed

Requirements are now stated once, in one catalog, in plain business language.
Three things follow from that.

### 1. The catalog no longer carries its own change history

A requirement used to accumulate a `Refined by <run>` block for every change that
touched it. One requirement had grown to roughly 145 lines that way — a changelog
living inside a specification. Those blocks are gone.

Nothing is lost, because none of it was only there:

| Question | Where it is answered now |
|---|---|
| Which changes touched this requirement? | The append-only event log — every completed change records the requirements it affected. |
| Why is it shaped this way? What was rejected? | The planning document that produced the change. |
| Which tests cover it? | The generated traceability matrix and the requirement-to-test manifest. |

**Requirement text carries no run identifier, no decision-record number and no
file path.** Those are the three things that rot: each names a record, a decision
or a file that moves independently of the capability it was describing. This is
enforced, not merely intended — see
`integration-tests/test_requirements_catalog_contract.py`.

### 2. Deep links into the catalog need EXPLICIT anchors

The traceability matrix links each requirement to its entry in the catalog using
the fragment `#fr-0101`. Anchors are matched **exactly** by the viewer.

A heading alone is not enough. `### FR-01.01 — /shipwright-run` produces the slug
`fr-0101--shipwright-run`, which does not equal `fr-0101`, so the link silently
scrolls nowhere and reports no error. Folded rows degrade worse.

So the catalog emits the anchor itself, immediately before the heading:

```markdown
<a id="fr-0101"></a>
### FR-01.01 — /shipwright-run
```

**If you generate or hand-edit a requirements catalog, do this too.** One anchor
per requirement, defined once — a duplicate makes the destination arbitrary.

### 3. Duplicate-ID detection (Group I check I4) is now GLOBAL

**This is the first of the two changes that can newly fail a project that was
passing** — the other is D2, below.

I4 used to allow the same requirement ID in two different requirement documents,
because it deduplicated on `(document, id)`. It now deduplicates on `id` alone,
across the whole catalog.

- **If your project has one requirements document** — the normal case, and the
  case this campaign is moving everyone toward — nothing changes.
- **If your project has several and they legally reuse ID numbers** (for example
  `FR-01.01` in two separate documents meaning two different things), I4 will now
  fail where it previously passed.

That is intentional and it is the point: one ID naming two requirements breaks
the identity that tests, the event log and the traceability matrix all depend on.
Tests are tagged with a bare requirement ID, so a reused number means a tag
cannot be resolved to one requirement.

**To fix it:** renumber so each ID is unique across the project. Never reuse a
number that has been retired — take the next free number counted over live and
retired requirements alike.

## Also changed: two audit checks stop reading green on nothing

Both were cases of a check reporting a clean result about a set it never looked
at. **One of the two can newly fail your audit** — read the D2 entry below.

### D-layer — no new block

("Active requirement missing a test at a required layer.") It used to report
`pass — every active FR is covered at its required layers` when the traceability
manifest declared no requirements at all. A reader could not tell that apart from
a genuinely fully-covered project.

It now reports `skip` with a detail naming the state. **A skip does not affect
the audit's exit code**, so nothing that passed before fails now.

### D2 — this one CAN newly fail your audit

("Recorded changes reference requirements that do not exist.") It used to `skip`
whenever the project had no readable requirements — precisely the state in which
every such reference is broken. It now reports them, as a failure.

**When it fires:** the requirements walk yields nothing readable **and**
`shipwright_events.jsonl` holds at least one entry with a non-empty
`affected_frs`. The audit then exits non-zero and the dashboard reads
`FAIL — drift found`.

**When it does not:** if no recorded change names a requirement, D2 still skips.
A project that simply has not written requirements yet is unaffected.

**If it fires, check which situation you are in — the report now tells you:**

The message names one of six states. It is the *same* wording the requirement
hygiene check (Group I) already uses, so the two never disagree about why your
requirements could not be read.

| What the report says | What it means | What to do |
|---|---|---|
| `no spec.md found under .shipwright/planning/<split>/` | You have no requirements document. The references really are dangling. | Write the requirements, or correct the recorded changes. |
| `contains no FR-shaped rows` | A document exists but holds nothing that looks like a requirement. | Add the requirements table. |
| `no table header naming a Priority column` | Your requirements **exist**; there is no header row for them to be read under. | Fix the table header. Do **not** touch the recorded changes — they are not the defect. |
| `no row id is canonical FR-XX.YY` | The table is fine; the IDs are not. | Fix the IDs — two digits either side. |
| `no row is wide enough to reach the Priority column` | Header and IDs are fine; rows are short. | Add the missing cells, or fix the header to match the rows. |
| `every FR row sits under '### Removed Requirements'` | Everything is retired. Nothing is broken. | Nothing, unless a recorded change should not have referenced a retired requirement. |

**If your table has more than one thing wrong with it, the wording softens** —
you will read *"some row ids are not canonical FR-XX.YY"* rather than *"no row id
is canonical"*, and likewise *"some rows are not wide enough"*. That is
deliberate: the absolute phrasing would be simply false once other rows failed
for other reasons. Search for the distinctive part of the sentence — *canonical*,
*wide enough*, *table header* — rather than the whole line. Either way the
message names only the IDs declined for the reason that decided the state, so
the ones it lists are the ones to fix first.

The middle four rows are why the message changed and not just the verdict.
Reporting *"changes reference requirements not in the current spec"* while naming
the very requirements the project has would send you to fix the wrong thing.

Promoting D-layer, or any of the other advisory checks, to a hard block is
deliberately separate work — it needs its own baseline.

## What did NOT change

- **The catalog path.** It stays at `.shipwright/planning/<split>/spec.md`. A
  requirements file placed directly under `.shipwright/planning/` is invisible to
  every directory walk in the toolchain, which reads as *zero requirements*,
  which reads as pass-or-skip nearly everywhere. The requirements checks would go
  dark while continuing to report green, and every feature change would
  simultaneously fail its finalization check. Do not move it.
- **Requirement IDs.** All fifteen in this repository survive unrenumbered, and
  the merge is pinned by a test that asserts exactly that.
- **The `Layers` column.** Every cell keeps its literal `(inferred)` marker.
  Layers remain non-authoritative: nobody has verified which layers each
  requirement actually needs, and a bare value would assert knowledge we do not
  have. Marked cells can be promoted individually as real test links are
  established; the reverse — walking back a claim of verified coverage — is not
  reversible in an audit record.
- **Artifact path registration.** No new entry was needed. `.shipwright/planning`
  is already a registered, completed migration, and the catalog sits under it.
  The step's own acceptance criterion anticipated an allowlist exemption for the
  paths the catalog quotes; compacting those paths *out* of the requirement text
  met the same goal without weakening the lint, which is strictly better.

## Known and deliberately not fixed here

**The FR-coherence check (S1 / S5) reports this catalog shape as incoherent.**

`compute_fr_coherence` calls a requirement coherent when its `### FR-…` heading
is followed by `**Description:**` and `**Acceptance Criteria:**` labelled blocks.
This catalog states each description in the **table** and each criterion as a
`- (E) Given … when … then …` bullet, so every requirement is reported as missing
both — including the ones that gained real criteria in this very step.

**If you adopt this catalog shape, expect the same report.** It is a WARN and
never affects an exit code, so nothing is gated on it.

It was left alone on purpose. Adding the labels would duplicate each description
— one copy in the table, one in the section — and two copies of one sentence
drifting apart is exactly what this migration removes. Renaming the headings so
the check stops matching would degrade the document to dodge a parser, and the
deep links land on those headings. The correct fix is to teach the check that a
heading whose ID is also a table row is a *detail section* rather than a second
definition; that is a change to a shared verifier every project consumes, and it
needs its own baseline rather than riding along inside a migration.

The false count is pinned by
`integration-tests/test_requirements_catalog_parsers.py`, so whoever fixes it is
forced to update this note rather than leave a stale one behind.
