# Eliciting Requirements — the shared grilling method

**Binding for every plugin that elicits a requirement from a human:**
`/shipwright-project` (a new project), `/shipwright-adopt` (confirming what was
read from an existing codebase), `/shipwright-iterate` (a change to a finished
project).

Requirements do not arrive finished. They arrive as a half-formed idea in one
person's head, in ordinary words, with the hard parts unspoken because the person
already knows them. This document is the **one method** all three plugins use to
pull that idea out completely — so the requirement that lands is one a product
owner can sign off and an auditor can trust, not the first plausible sentence the
conversation produced.

It replaces three divergent interview descriptions with a single discipline. Each
plugin keeps only what is genuinely specific to it (§12); the method, the
coverage guarantee, and the question bank live here.

> **The one rule this whole document exists to enforce:** you have not finished
> eliciting a requirement until **every dimension of its context (§8) is either
> answered or explicitly recorded as an unconfirmed assumption.** Everything else
> is how you get there.

---

## 1. The grilling loop

> *"Interview me relentlessly about every aspect of this until we reach a shared
> understanding."*

Elicitation is an interview, not a form. Walk each branch of the decision tree,
resolving the dependencies between decisions **one at a time**. Keep going until
you and the person share the same picture — not until they stop talking. A vague
answer is not an answer; it is the next thing to grill.

This is relentless by design. The failure mode it prevents is the shallow
interview that captures the happy path, misses the edge cases and the *why*, and
leaves a requirement that reads fine and means nothing.

## 2. One question at a time, each with a recommendation

- **One question, then wait.** *"Asking multiple questions at once is
  bewildering."* Put a single question to the person and wait for the answer
  before the next. Never dump a numbered list of ten questions — that is not an
  interview, it is a form, and it produces form-quality answers. In our stack the
  one-question-at-a-time turn is an `AskUserQuestion` call (the host blocks on it
  and waits for the reply).
- **Every question carries a recommended answer.** Offer your best answer with
  the question, so the person corrects a concrete proposal instead of authoring
  from a blank page. This is exactly the house rule in `CLAUDE.md` ("lead with
  the functional meaning, give a recommendation") — phrase it so a product owner
  can answer without decoding jargon.

## 3. Look it up — facts are found, not asked

> *"If a fact can be found by exploring the environment (filesystem, tools, etc.),
> look it up rather than asking me. The decisions, though, are mine — put each one
> to me and wait for your answer."*

Split every open point into a **fact** or a **decision**:

- A **fact** — what framework this is, which endpoints exist, what the current
  limit is set to, whether a file is gitignored — you **look up** in the code and
  tools. Asking a person to recite what the repository already states wastes the
  interview and invites a wrong answer from memory.
- A **decision** — what the product *should* do, which trade-off to take, what a
  term *means* — is the person's to make. Put each one to them and wait.

For `/shipwright-adopt` and `/shipwright-iterate` this "look it up first" step is
literally a scan of the real code (§6); the interview then spends its budget only
on what the code cannot answer.

## 4. Sharpen the language against the glossary

Imprecise language is where requirements rot. Two moves, taken the moment fuzzy
language appears — do not wait:

- **Challenge a term against the glossary.** When the person's word clashes with
  the project's `CONTEXT.md`, flag it immediately: *"Your glossary defines
  'cancellation' as X, but you seem to mean Y — which holds?"*
- **Replace a vague word with a precise one.** *"You said 'account' — do you mean
  the paying Customer or the logged-in User?"* Force the distinction before it
  hardens into a requirement that two readers understand two ways.

The project's evolving vocabulary lives in `CONTEXT.md` (§7) — the target
project's **domain** glossary, which is a different artifact from the framework's
`shared/glossary.md`. The format is `shared/context-format.md`.

## 5. Stress-test with concrete scenarios

Abstract agreement hides disagreement. When a relationship or a rule is stated,
**invent a concrete edge-case scenario that forces precision about the
boundaries:**

> "So a customer cancels an order that has already partly shipped — does the
> refund cover the shipped items, and does the requirement still hold?"

Each scenario either confirms the boundary or exposes a case nobody had decided.
The cases it exposes are exactly the acceptance criteria the requirement was
missing.

## 6. Cross-check against the code

The most valuable contradiction is between what the person *says* and what the
code *does*. Surface it plainly:

> "Your code cancels whole orders, but you're describing partial cancellation as
> possible — which is the real requirement?"

For a new project there is no code yet, so this reduces to §5. For adopt and
iterate it is the **completeness scan**: read the actual behaviour, list where it
diverges from what the person is describing, and put each divergence to them as a
decision. This is the step that turns "derived from the code, unconfirmed" into a
requirement someone has actually stood behind.

## 7. Capture as you go — CONTEXT.md and ADRs

Document **during** the conversation, not after — batching loses the resolution
while it is fresh.

- **`CONTEXT.md`** — every term you sharpen (§4) is written into the project's
  domain glossary the moment it is resolved. `CONTEXT.md` is a **pure glossary,
  totally devoid of implementation detail** — never a spec or a scratch pad. Its
  format is `shared/context-format.md`.
- **ADRs — sparingly.** Record the reason behind a choice **only when all three
  hold**: it is *hard to reverse*, *surprising without context* (a future reader
  will question it), and *the result of a genuine trade-off* (real alternatives
  existed). If any one is missing, skip the ADR — a decision record for every
  magic number is bloat, not rationale.

This section is where **Rewritability** is earned: the *why* behind a
hard-to-reverse choice is captured at the moment it is decided, linked from the
requirement, so the implementation can later be re-derived from intent — not
reverse-engineered from the code. Acceptance criteria say *what*; the ADR says
*why*.

## 8. The coverage checklist — the completeness contract

This is the centralized guarantee: **the same set of dimensions must be covered
wherever a requirement is elicited**, so no surface grills more shallowly than
another. A requirement is **not finished** until, for each dimension below, the
answer is either **captured** or **explicitly recorded as an unconfirmed
assumption** (`Basis: assumed`, the honest cell `shared/fr-authoring.md` §4a
already defines). Silently leaving a dimension blank is the one thing this method
forbids.

| Dimension | The question it answers | Where a gap is recorded |
|---|---|---|
| **Purpose** | What does this do for whoever uses it, and why does it matter? | the FR description |
| **Boundaries & edge cases** | Where does it start and stop? What are the corner cases (§5)? | acceptance criteria |
| **Failure behaviour** | What happens when it goes wrong — what is prevented, what is kept? | acceptance criteria |
| **Glossary terms** | Which terms did it introduce or sharpen (§4)? | `CONTEXT.md` |
| **Rationale (the *Warum*)** | Why this way, if the choice was hard to reverse and surprising (§7)? | an ADR, linked |
| **Out of scope** | What will this explicitly **not** do? | the requirement's "out of scope" note |

**The stop-condition, stated once:** before the requirement is treated as
settled, every row above is answered, or its cell is `Basis: assumed` with the
guess recorded as a guess. A dimension you could not get an answer to is a known
gap to close, not a silence to move past. When in doubt, `Basis: assumed` is
always the honest answer — never invent a confident one.

## 9. Confirm before acting

> *"Do not act on it until I confirm we have reached a shared understanding."*

When the checklist (§8) is satisfied, play back the shared understanding — the
capability, its boundaries, its failure behaviour, the assumptions still open —
and wait for the person to confirm it. Only then write the requirement. The
confirmation is the hand-off from *their* mental model to *the recorded one*; skip
it and you have recorded your own guess.

## 10. Where the output lands

Matt Pocock's method ends in a PRD. **Ours does not.** The loop ends by writing,
per requirement:

- a **functional-requirement row** and its **assertion-shaped acceptance
  criteria** (`- (E) Given … when … then …`), authored under the rules in
  **`shared/fr-authoring.md`** — plain business language, capability altitude,
  MINT-vs-FOLD, `Basis` and `Layers` cells;
- any sharpened terms into **`CONTEXT.md`**;
- any hard-to-reverse *why* into a linked **ADR**.

Take the full technique from Pocock; land it in our artifacts, not a PRD.
`fr-authoring.md` governs *how the row reads*; this document governs *how its
content was elicited*. They compose: grill to completeness here, write to
altitude there.

## 11. The shared question bank

Recommended starting questions per checklist dimension (§8). They are a floor,
not a script — follow the answers wherever they go, and always attach a
recommended answer (§2).

- **Purpose** — "In one sentence, what can someone do after this exists that they
  couldn't before? Who is 'someone'?"
- **Boundaries & edge cases** — "What's the smallest and the largest case this
  must handle? What happens right at the edge — empty, huge, concurrent, retried?"
- **Failure behaviour** — "When this fails, what must still be true? What is
  prevented, and what is preserved?"
- **Glossary terms** — "You used the word '…'. Is that the same '…' the glossary
  already defines, or a new meaning?"
- **Rationale** — "Is this choice hard to undo later? Was there a real
  alternative you rejected? If yes to both, why this one?" (only then an ADR)
- **Out of scope** — "What might someone reasonably expect this to do that it
  deliberately will **not**?"

## 12. How each plugin applies it

The method, the checklist and the question bank above are shared and **may be
added to but never skipped**. Each plugin keeps only its genuinely
surface-specific questions, layered on top:

- **`/shipwright-project` (greenfield)** — natural split boundaries, ordering and
  dependencies between splits, and uncertainty mapping (which parts need a
  dedicated planning exploration). It also surfaces its inferred assumptions
  (stack, persistence, auth) up front so they can be corrected cheaply.
- **`/shipwright-adopt` (brownfield)** — *infer-from-the-code first* (§3/§6): the
  vast majority of facts come from Layer-1 detection; the interview asks only the
  strategic questions the code cannot answer (profile, scope, nested projects)
  and then **confirms the requirements derived from the code** in business
  language rather than leaving them as guesses.
- **`/shipwright-iterate` (change to a finished project)** — the scope of *this
  change*, and the MINT-vs-FOLD question (`fr-authoring.md` §3): is this a new
  capability, or a change to one that already has a requirement?

A plugin's own reference doc names these specifics and cites this module for the
method itself.

---

> **Attribution.** The grilling loop and the domain-modeling discipline are
> adopted, with the technique taken in full, from Matt Pocock's agent skills —
> `grilling`, `domain-modeling`, and their `grill-with-docs` wrapper
> (https://github.com/mattpocock/skills, MIT, © Matt Pocock). The verbatim rules
> ("one question at a time", "look up facts", "confirm before acting", the ADR
> three-condition filter, "CONTEXT.md is a pure glossary") are his; the adaptation
> to Shipwright's FR-row + assertion-shaped-AC artifacts, and the §8 coverage
> contract, are ours.
