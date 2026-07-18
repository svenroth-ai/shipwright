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

**Grouping is the split — greenfield needs no `Area` column.** `/shipwright-project`
already decomposes into splits (`02-task-board/`, `04-terminal/`), so the group
is carried by the ID and by the file the FR lives in.

An `Area` column is a **brownfield repair**: `/shipwright-adopt` puts everything
it discovers into one split, so the ID alone can no longer express the grouping
and it has to be restored as a column. Do not add `Area` to a greenfield spec —
create the right split instead.

---

## 5. The name

1. A capability phrase, present tense, from the user's or system's standpoint.
2. No `GET`/`POST`/`PUT`/`PATCH`/`DELETE`, no `snake_case` symbols, no file
   paths, no ADR numbers, no iterate slugs. Those go to the Origin column,
   the acceptance criteria, or `architecture.md`.
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

**Advisory** means the finding is reported with its count and IDs but does not
change the audit's verdict or exit code — an existing spec can carry historical
violations and clean up gradually without reddening CI. Fix them when you next
touch the row. `I4` is different: two rows claiming one FR ID is an objective
defect (it breaks the identity that tests and the event log depend on), so it
fails for real.

`I1` reports `skip` on a spec shape with no Name column — the §5 fence has
nothing to examine there, and reporting `pass` would be a false green.

Not linted, deliberately: §5.3 (name length) and §5.4 (one capability per FR)
need editorial judgement, and a wrong automated verdict would be worse than
silence.
