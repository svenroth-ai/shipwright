# Writing Functional Requirements

**Binding for every plugin that authors or edits an FR row:**
`/shipwright-adopt`, `/shipwright-project`, `/shipwright-iterate`.

A Functional Requirement says **what the product does for whoever uses it**.
It is read by product owners, auditors, and new joiners — not only by engineers.
Everything about *how* it is built belongs somewhere else (see §6).

---

## 1. Plain language — the primary rule

> **The reader test:** could someone who has never seen the code — a product
> owner, an auditor, a new colleague — read this row and correctly say what the
> product does and what it guarantees?

If the answer is no, the row is wrong, however accurate it is. This is the test
that decides; the fences in §2 and §5 are only the mechanical shortcuts to it.

**Write:**

- the capability from the user's or the system's standpoint;
- every behavioural guarantee that matters — what is prevented, what is kept,
  what happens when it goes wrong;
- ordinary words. If a technical term is genuinely unavoidable, add a short
  plain gloss in parentheses: *"idempotent (safe to run twice)"*.

**Never drop a guarantee to sound plainer.** Plain wording, full meaning. If a
plain sentence would lose a real constraint, the sentence is not finished yet —
rewrite it, don't trim it.

### Keep the guarantee, drop the mechanism

| ❌ Implementation prose | ✅ Plain business language |
|---|---|
| `Persisted at ~/.shipwright-webui/settings.json with proper-lockfile-guarded writes.` | Settings are saved safely, so two open tabs can't corrupt each other's changes. |
| `Session state is held client-side; the server is stateless (ADR-034).` | The server keeps no memory of where you were, so several tabs just work. |
| `Renames take effect on the next launch via Claude's --name flag.` | Renaming a task takes effect the next time it starts. |
| `Walks unmatched tool_use ids in the JSONL to derive pending AskUserQuestion blocks.` | Shows every question the assistant is waiting on, so no session sits blocked unnoticed. |

Each ✅ keeps the guarantee (writes are safe, tabs are independent, renames are
deferred, nothing sits blocked) and drops only the mechanism.

---

## 2. Altitude — a capability, not a route and not a change

An FR is a **stable, observable capability or guarantee**. These are *not* FRs:

| Not an FR | Where it belongs |
|---|---|
| a single HTTP endpoint | `architecture.md` (the interface surface), and its behaviour as acceptance criteria on the FR it serves |
| a bug fix, polish pass, or "Phase 2 of …" | an acceptance-criteria line on the existing FR |
| a refactor with no observable change | the ADR / decision log — Spec Impact `NONE` |
| an ADR or architectural choice | `architecture.md` |

**Altitude test:** can a non-technical person read the *name* as something the
product **can do** or **guarantees**? If the name contains `GET`/`POST`, a
`snake_case` symbol, an ADR number, or the words *completes / modifies /
replaces FR-x*, it is a route or a change — not a requirement.

---

## 3. Mint or fold — decide before writing a row

Before adding an FR row, answer one question:
**is this a capability the product did not have before?**

- **FOLD** — the change *completes, polishes, fixes, extends,* or is
  *"Phase N of"* something that already exists.
  → **Do not add a row.** Append acceptance-criteria lines to the existing FR
  and record it as Spec Impact `MODIFY` with that FR in `--affected-frs`.
- **MINT** — a genuinely new, user- or system-observable capability.
  → Add one row, per §4 and §5.

Folding is the common case. A spec that grows one FR per unit of work stops
describing the product and starts duplicating the changelog.

**Worked example.** Four rows had accumulated for one capability:

```
❌ FR-01.38 Responsive tablet layout
   FR-01.39 Phone drawer
   FR-01.41 Density polish (modifies FR-01.38/39)
   FR-01.64 iOS zoom fix
```

```
✅ FR-01.38 Works on tablet and phone
     - [ ] … tablet layout …
     - [ ] … phone drawer …
     - [ ] … spacing corrections …
     - [ ] … no unwanted zoom on iOS …
```

One capability, four rounds of work recorded as acceptance criteria. The change
history already lives in the commits, the changelog, and `shipwright_events.jsonl` —
it does not need a second home in the requirements table.

---

## 4. Numbering and grouping

**ID scheme — `FR-{group}.{NN}`.** The group is the planning split; `NN` is the
requirement's number inside it. `FR-04.02` reads as *"second requirement in
split 04"*.

- A new FR takes the **next free `NN` in its split**: the highest number in use
  plus one, counting **both live and removed rows** so a retired number is never
  reused. Never guess a number.
- **IDs are permanent.** They are referenced from tests (`@FR` tags), from the
  append-only `shipwright_events.jsonl`, and from released changelogs. Renaming
  and regrouping are always allowed; renumbering is not.
- If two parallel iterates pick the same number, the duplicate is a **conflict
  to resolve at merge**, not a number to keep. Audit check `I4` flags it.

**Grouping is the split, and `Area` is that grouping's display label — not a
second axis.** `/shipwright-project` already decomposes into splits
(`02-task-board/`, `04-terminal/`), so the group is carried by the ID.

`Area` is **rendered from the ID's group digit**, never stored independently:
`FR-03.xx` belongs to split `03-…` and its `Area` cell is that split's name.
Two grouping axes for one fact diverge; a computed label cannot.

- **Every spec carries the `Area` column**, greenfield and brownfield alike —
  it is part of the one converged table shape (§4a) both generators emit, and
  the column list is not optional.
- **What greenfield still does NOT need is `### Area` sub-sections.** Add those
  only when one split genuinely holds more than one area. A greenfield split
  already carries its grouping in the ID, so in the normal case the sections
  would restate what the IDs already say.
- If you find yourself choosing an `Area` that disagrees with the ID's group,
  **the ID is authoritative** and the requirement is filed in the wrong split —
  create the right split rather than relabelling the cell. (The renderer will
  not follow you: on disagreement it emits `Group NN`, so the inconsistency
  shows up in the table.)

---

## 4a. The row: one shape, and two cells that are graded

Every FR table, greenfield and brownfield, has one shape:

```
| ID | Area | Name | Priority | Description | Basis | Layers |
```

Do not add, drop, rename or reorder a column. Columns are resolved by NAME, so
a renamed column is not a cosmetic choice — it is a column that stopped existing.

### `Basis` — how we know this requirement

One value, from a closed set. **A value outside it is a hard audit failure**
(check `I5`), because that is a typo rather than a special case.

| Value | Use when |
|---|---|
| `interview` | a human told us |
| `code` | it was read from source |
| `observed` | it was seen in the running application |
| `tests` | it was derived from existing tests |
| `assumed` | **nobody has confirmed it — it needs checking** |
| `other` | a genuine special case; write `other: <reason>` |

`assumed` is the one that earns its keep. Reach for it whenever you are
tempted to guess: if an interviewee could not recall *why* a limit is 90 and
you wrote down a plausible number, that requirement's basis is `assumed`, not
`interview`. Recording the guess as a guess is the whole point.

Known values take **no qualifier** — write `code`, never `code (auth.ts)`.
`other` never blocks; a bare `other` is only nagged for its missing reason. A
**blank** cell does fail, because declaring the column is opting in and
`assumed` is always available as the honest answer.

**How the cell is normalised before comparison** (one rule, so producer output
and a hand-authored spec cannot diverge): surrounding whitespace is trimmed,
wrapping Markdown emphasis (`` ` ``, `*`, `_`) is stripped, and the result is
lowercased. So `` `Code` ``, `  code  ` and `**CODE**` are all `code`. Nothing
else is normalised — comparison is against the exact ASCII tokens above, so a
Unicode lookalike (a Cyrillic `с` in `сode`) is malformed and **fails loudly**
rather than being silently accepted. That is the intended direction: this column
exists to be checkable.

### `Layers` — which test layers this must be covered at

From `{unit, integration, e2e}`, comma-separated. Two forms, and the difference
is not cosmetic:

| Form | Means | Consequence |
|---|---|---|
| `unit, e2e` (bare) | **you are declaring it.** | **Binding.** A missing layer is a HARD coverage failure that exits non-zero — not a warning. |
| `unit, e2e (inferred)` | **nobody has verified these layers.** Usually a tool wrote it (adopt, a migration), because a tool is usually what produces an unverified guess — but the marker describes the cell's STANDING, not who typed it, and a human may write it honestly. | Advisory. Reported, never blocking. |

**Write the bare form only when the tests exist or you are about to write them
in the same iterate.** Declaring `unit, e2e` on a requirement with no `@FR`-
tagged tests hard-fails finalization on the spot, and there is no bypass — no
env var, no flag, no label. That is intended: a human declaring layers for a
capability they are building should be held to it.

**When the layers have not been verified, `(inferred)` is the honest cell** and
it is the one that does not block. `Basis: assumed` expresses the same *kind* of
honesty about a different fact — do not substitute one for the other: `Basis`
records how we know the **requirement**, `Layers` records what it must be
**tested** at. A requirement can be `Basis: interview` and still have entirely
unverified layers. Only the literal parenthesised word counts — `(auto)` and
`(guess)` do **not** match and are read as a binding declaration.

Mind the space: `unit (inferred)` is correct, `unit(inferred)` is not — the
second parses as one unrecognised token and the requirement silently ends up
with no required layers at all.

---

## 5. The name

1. A capability phrase, present tense, from the user's or system's standpoint.
2. No `GET`/`POST`/`PUT`/`PATCH`/`DELETE`, no `snake_case` symbols, no file
   paths, no ADR numbers, no iterate slugs. Those go to the acceptance
   criteria or `architecture.md`. **Not** to `Basis` — that column takes one
   value from a closed vocabulary (§4a) and nothing else; the file path a
   requirement came from is exactly what it replaced.
3. About six words. Detail belongs in the description.
4. One FR, one capability. A name joining two unrelated capabilities with
   "and" is usually two FRs.

| ❌ | ✅ |
|---|---|
| `Pending tool_use list (GET)` | Pending questions |
| `Build copy-command for terminal launch (POST)` | Start or resume a task |
| `Embedded terminal — pty + WebSocket bidi + disk-backed scrollback (ADR-067)` | Embedded terminal |
| `Per-run data join (runId → FRs/tests/derived-gates/phase-timings)` | Per-run metrics |

---

## 6. Where the "how" goes instead

Nothing is being thrown away — it is being filed correctly.

| Detail | Home |
|---|---|
| file paths, module and symbol names | `architecture.md`, the code |
| the endpoints serving a capability | `architecture.md` — the FR states what the capability does, not how it is reached |
| why it was built this way | the ADR / decision log |
| which iterate changed what | commits, changelog, `shipwright_events.jsonl` |
| what must be true for it to be done | the FR's acceptance criteria |

---

## 7. Enforcement

Compliance audit **Group I — Requirement Hygiene** reports drift against this
document.

| Check | Flags | Effect |
|---|---|---|
| `I1` | an FR name carrying a verb, symbol, path, ADR number, or iterate slug | advisory |
| `I2` | an FR description carrying implementation detail | advisory |
| `I3` | an FR that only describes a change to another FR — a fold candidate | advisory |
| `I4` | the same FR ID used twice in one split, or reuse of a retired number | fails the audit |
| `I5` | a `Basis` value outside the §4a vocabulary, or a blank cell in a table that declares the column | fails the audit |

**Advisory** means the finding is reported with its count and IDs but does not
change the audit's verdict or exit code — an existing spec can carry historical
violations and clean up gradually without reddening CI. Fix them when you next
touch the row. `I4` and `I5` are different: two rows claiming one FR ID breaks
the identity that tests and the event log depend on, and a `Basis` value outside
a closed vocabulary is a typo rather than a special case. Both fail for real.

`I5` reports `skip` on a spec with no `Basis` column at all — that is every spec
written before the column existed, and scoring its absent values would make
adopting the column a breaking change. Within the check, `other` is always
advisory: an escape hatch that blocks is not one.

`I1` reports `skip` on a spec shape with no Name column — the §5 fence has
nothing to examine there, and reporting `pass` would be a false green.

Not linted, deliberately: §5.3 (name length) and §5.4 (one capability per FR)
need editorial judgement, and a wrong automated verdict would be worse than
silence.
