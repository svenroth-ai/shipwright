# The grill-trace record — evidence that elicitation happened

**Companion to `shared/requirement-elicitation.md` §8/§9 and the design at
`.shipwright/planning/campaigns/2026-07-24-req3-grill-trace-enforcement-DESIGN.md`.**
A structured record the elicitation surface writes **live, during** the
interview — one file per elicited requirement — so the grilling method's
guarantee is checkable instead of prompt-only.

This document is the schema. The producer (writer) and reader
(completeness gate) are `shared/scripts/tools/write_grill_trace.py` and
`shared/scripts/tools/verify_grill_trace_completeness.py`; the shared
data model both go through is `shared/scripts/tools/grill_trace_format.py`
— read/write it through that module, never hand-parse the JSON.

## 1. Where it lives

`{planning_dir}/grill-traces/<requirement_key>.json`, one file per elicited
requirement, where `{planning_dir}` is the project's `.shipwright/planning/`
(the same directory `shipwright_project_interview.md` and
`project-manifest.md` live in — not inside a split subdirectory, since the
trace is written during the interview, before a requirement has been
assigned to a split).

`<requirement_key>` is a lower-kebab-case slug (`^[a-z0-9]+(-[a-z0-9]+)*$` —
validated at write time; also forecloses any path-separator/`..`
filesystem-boundary risk, since neither can ever match) the interviewer
chooses at the moment a requirement's shared understanding is confirmed
(§9) — the same words that become the FR row's `Name` column once spec
generation runs. This pairing **is enforced**, not just eyeballed: the
gate's `fr_trace_coverage` check (§5) slugifies every spec.md FR row's
`Name` cell with the exact same rule and fails when no grill-trace
`requirement_key` matches it.

`grill_trace_fr_coverage.slugify()` lowercases, replaces runs of
non-`[a-z0-9]` with a single hyphen, and strips leading/trailing hyphens —
it does **not** transliterate. An FR `Name` containing an apostrophe or a
diacritic (`"Editor's picks"`, `"Café order"`) collapses the punctuation to
a hyphen or drops it rather than substituting an ASCII equivalent
(`café` → `caf`, not `cafe`) — an interviewer picking a `requirement_key`
by hand should avoid apostrophes and non-ASCII letters in the requirement
text they slug from, or the two slugify passes (this one and spec
generation's, if they ever diverge in implementation) risk producing two
different strings for what a person would call the same name.

## 2. The shape

```json
{
  "requirement_key": "login-rate-limit",
  "requirement_text": "The system SHOULD rate-limit login attempts to 5 per minute per IP.",
  "surface": "project",
  "evidence": [
    "turn 4: user described repeated failed sign-ins as a concern",
    "turn 6: user confirmed 5/minute as a starting guess, unconfirmed"
  ],
  "dimensions": {
    "outcome": "answered",
    "purpose": "answered",
    "boundaries": "answered",
    "failure": "answered",
    "glossary": "n/a:no new term introduced by this requirement",
    "rationale": "n/a:not hard to reverse, not surprising",
    "out_of_scope": "answered"
  },
  "fit_criterion": "a sixth failed sign-in within a minute from one IP is refused",
  "glossary_delta": [],
  "confirmed_by": "user confirmed the shared understanding in turn 7"
}
```

| Field | Type | Meaning |
|---|---|---|
| `requirement_key` | string | lower-kebab-case slug, unique per requirement, non-blank |
| `requirement_text` | string | the requirement as currently elicited (the sentence the FR row will carry), non-blank |
| `surface` | string | which plugin elicited it — `project` \| `adopt` \| `iterate` (closed vocabulary; only `project` is wired as of P4.2) |
| `evidence` | array of strings | what was actually read/asked — interview turns for `project`'s surface; code files read for `adopt`/`iterate`. Proves "look it up" happened. Non-empty. |
| `dimensions` | object | exactly the seven keys below, each `"answered"` \| `"assumed:<reason>"` \| `"n/a:<reason>"` |
| `fit_criterion` | string or null | the yes/no measure (Volere fit criterion) for the **outcome** dimension. Required (non-blank) whenever `dimensions.outcome == "answered"`; omit/null otherwise. |
| `glossary_delta` | array of `{"term", "recorded_in"}` | terms sharpened during this requirement's elicitation and where each was recorded (`CONTEXT.md` for `project`/`iterate`) |
| `confirmed_by` | string | the sign-off (§9) — the hand-off from the person's mental model to the recorded one. Non-blank. |
| `terms_used` | array of strings | the domain terms this requirement's text depends on, declared by the interviewer (not derived by scanning prose — see the honesty guard below). May be empty. |

### The seven dimensions (`requirement-elicitation.md` §8, in table order)

`outcome`, `purpose`, `boundaries`, `failure`, `glossary`, `rationale`,
`out_of_scope`. Every key must be present; a missing key is the same
STOP as a blank one.

## 3. Honesty guard — completeness only, never prose quality

The gate (`verify_grill_trace_completeness.py`) checks that a trace is
**structurally complete** — every dimension carries one of the three
closed-vocabulary shapes, an `assumed` reason exists where required, an
outcome carries a fit criterion, every declared term resolves. It never
reads `evidence`, `fit_criterion`, or `confirmed_by` for *quality* — a
one-word definition and a terse assumption reason both pass, as long as
the shape is present. "Did the agent grill well" has no oracle and stays
untestable by design; what is gated is that a trace exists and nothing
drifted.

This is also why `terms_used` is a field the interviewer **declares**
rather than something the gate derives by scanning `requirement_text` for
capitalized words or repeated nouns: free-text term extraction is a
judgment call (which words are "terms" at all), and judgment calls are
exactly what this gate must not make. Declaring the list keeps the
undefined-term check a plain set-membership test.

## 4. The undefined-term check

For each term in `terms_used`, the gate checks it appears — **exact-case,
exact-prose**, no folding (`context_md_format.py`'s own matching contract)
— in `shared/glossary.md`'s bold entry headings, or in the target
project's `CONTEXT.md` via `context_md_format.read_terms()` (the sanctioned
reader — never re-derive or fork the `CONTEXT.md` parser). A term in
neither is the **undefined term** STOP.

**A missing `CONTEXT.md`** (P4.1's producer hasn't run yet, or a genuinely
fresh project) contributes zero terms and is never treated as "nothing to
check" — a declared term then has only `shared/glossary.md` to resolve
against, so the STOP still fires rather than silently passing. The gate
fails **strict**, never lenient, on an absent glossary source.

## 5. Coverage — not one of the four STOPs, but not advisory either

Additional checks the gate runs, each under its own name so none is ever
confused with the four closed-vocabulary STOPs above:

- **`grill_trace_coverage`** — an interview transcript exists but zero
  grill-trace records were written at all (the SKIPPED-interview case).
- **`fr_trace_coverage`** (`grill_trace_fr_coverage.py`) — once spec
  generation (Step 6) has minted FR ids, every live FR row's `Name` cell
  (slugified with the same rule as `requirement_key`, §1) must match some
  grill-trace file. Catches a PARTIALLY recorded interview the coverage
  check above cannot see (some requirements traced, one silently skipped).
  SKIPPED entirely before any spec.md exists.
- **`glossary_source_available`** (`grill_trace_glossary.py`) — the
  framework's own `shared/glossary.md` is missing. Unlike an absent
  `CONTEXT.md` (§4, a legitimate fresh-project state), this means the
  Shipwright install itself is broken.
- **`glossary_delta_declared`** — a term the trace records sharpening
  (`glossary_delta`) but never lists in `terms_used`. A narrow,
  self-consistency slice of the honesty guard's declared-list limit (§3):
  it catches the case where a trace contradicts itself, not the case
  where a term is omitted from both lists (still possible by design — see
  §3).

All are **structural presence/consistency checks**, not content
judgments — the same honesty guard (§3) applies to them.

**Known limitation — `fr_trace_coverage`'s slug join (second-round external
plan review, P4.2):** the join is exact-string equality between
`slugify(FR row's Name)` and an existing grill-trace `requirement_key`, not
a tracked, producer-enforced identity carried from interview output into
the generated FR row. Two consequences, both accepted rather than built
around in this sub-iterate (scope: wire the four DESIGN.md STOPs onto
`/shipwright-project`, not redesign spec generation's FR-naming pipeline):

1. **Collision:** two FR `Name` cells that slugify to the same string (for
   example differing only in whitespace or punctuation:
   `"Login (SSO)"` / `"Login SSO"`) are indistinguishable to the join —
   one grill-trace can appear to cover both.
2. **Orphan traces:** a grill-trace whose `requirement_key` matches no
   live FR row is never itself flagged; the check only walks FR rows
   looking for a match, not traces looking for a landing FR.

Neither produces a false PASS on the four closed-vocabulary STOPs
(§ this section is deliberately not one of them) — the failure mode is a
missed or ambiguous coverage signal, not a silently-accepted incomplete
trace. Follow-up tracked as a triage card rather than blocking P4.2.

---

> Companion artifacts: `shared/context-format.md` (the same Language-entry
> convention this schema's `glossary_delta.recorded_in` points at),
> `shared/requirement-elicitation.md` §8/§9 (the method this record proves
> was followed).
