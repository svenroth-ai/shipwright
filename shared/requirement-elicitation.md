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
> eliciting a requirement until **every dimension of its context (§8) is
> answered — or, only where the answer genuinely cannot be obtained, explicitly
> recorded as an unconfirmed assumption.** Marking something assumed while
> someone who could answer it is in the conversation is not honesty, it is
> declining to ask. Everything else is how you get there.

---

## 0. The order — do it in this sequence

The sections below are the method's *parts*; this is the **order to run them
in**, and the order is load-bearing — run them in whatever sequence feels natural
and the analysis eats the interview, because reading produces findings faster
than asking does. Every failure named below was observed in this method's own
acceptance round (REQ-3 Phase 2, 2026-07), by an agent who had read this document
and was deliberately dogfooding it.

1. **Name what the capability produces — write that criterion first (§8).**
   Before any analysis, before reading a line of code: *what exists afterwards
   that did not before?* **The most common failure** — six of eight requirements
   were signed off without it, because criteria derived from analysis inherit the
   analysis's bias: refusals and edge cases are what *stand out* when reading
   code, while the core capability is too self-evident to write down. A
   requirement whose first criterion is a refusal or an edge case is the
   signature.
2. **Look up the facts (§3, §6)** — read the code, not the description of it.
3. **Show the divergence** before writing anything: enforced · prompt-only ·
   contradicted.
4. **Negative-space pass (§8.1)** — what should it guarantee that it doesn't?
5. **Stress-test with scenarios (§5)** — the minimum is two, and they are put to
   the person, not answered by you.
6. **The out-of-scope dimension explicitly (§8)** — what will this *not* do?
7. **Capture and cross-check glossary terms (§4)** — including against terms
   that already exist.
8. **Run the coverage checklist (§8) and show the criteria** before calling the
   requirement done.

**This is instruction only, and instruction is not enough** — the same round had
an agent actively dogfooding this document still skip §1, §4 and §5 until a human
noticed. A prompt-only guarantee cannot be repaired with more prompt; the fix is
a produced trace plus a completeness gate, which is why that exists as a work
unit and not as another paragraph here.

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

Imprecise language is where requirements rot. Three moves. The first two are
taken the moment fuzzy language appears; the third has a **concrete trigger**,
because "the moment fuzzy language appears" is not something anyone notices
about their own writing:

- **Trigger: every time a term is captured, check it against the terms already
  there.** Not "append to the list" — read the neighbouring entries and ask
  whether this word already means something else here. Ten terms appended in one
  pass (§0) introduced a real ambiguity: `Producer` was already defined as a
  **rule** (exactly one code path may write an artifact); the new entry reused it
  as a **description** (whatever writes this format, possibly several). One word,
  two meanings, added by the person holding the glossary. A list that is only
  ever appended to becomes a collision generator.

- **Challenge a term against the glossary.** When the person's word clashes with
  the project's `CONTEXT.md`, flag it immediately: *"Your glossary defines
  'cancellation' as X, but you seem to mean Y — which holds?"*
- **Replace a vague word with a precise one.** *"You said 'account' — do you mean
  the paying Customer or the logged-in User?"* Force the distinction before it
  hardens into a requirement that two readers understand two ways.
- **Then keep using it.** Sharpening a term is worthless if the next paragraph
  reaches for a synonym. Once a term is settled, it is the only word for that
  thing — and inventing a "plainer" alternative mid-flight is the same defect as
  leaving the original vague, because now the reader has two words and no way to
  know they mean one thing. If a settled term genuinely reads badly to a
  non-technical audience, change the definition and use the new word
  *everywhere*; do not run both.

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

**The minimum is two per requirement, put to the person.** A number, because as
an encouragement this produced **zero** scenarios across six requirements (§0),
while three on the seventh found more than six walks of code-reading had.
Answering your own scenario does not count — the value is the case the other
person decides differently than you assumed. Record which were put and what each
settled; one that exposed nothing is still evidence the boundary was tested.

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

> **Reading a prompt is not reading the code.** An agent instruction file — a
> `SKILL.md`, a reference doc — is the **claim under test**, not evidence for it.
> Checking a requirement against the document that asserts the same thing is
> reading the claim twice. Open what actually runs: the scripts, the libraries,
> the hooks, the tests.

Sort every claim into exactly one of three, and carry the label forward — the
difference decides what can ever be tested, and skipping this step is how a
guarantee nobody implemented survives review:

| Verdict | Meaning | Consequence |
|---|---|---|
| **enforced** | a mechanism in the code makes it true | a behavioural test can pin it |
| **prompt-only** | it exists solely as an instruction | **no behavioural test is possible.** Only a drift test asserting the instruction is still present. If a deterministic check *could* be built, that is a gap to record — not a reason to state the guarantee less honestly |
| **contradicted** | the code does something else | the requirement or the code is wrong; resolve it with the person before writing |

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
| **Outcome** | **What must exist afterwards for this to have succeeded — and how would you tell it is any good?** | acceptance criteria |
| **Purpose** | What does this do for whoever uses it, and why does it matter? | the FR description |
| **Boundaries & edge cases** | Where does it start and stop? What are the corner cases (§5)? | acceptance criteria |
| **Failure behaviour** | What happens when it goes wrong — what is prevented, what is kept? | acceptance criteria |
| **Glossary terms** | Which terms did it introduce or sharpen (§4)? | `CONTEXT.md` |
| **Rationale (the *Warum*)** | Why this way, if the choice was hard to reverse and surprising (§7)? | an ADR, linked |
| **Out of scope** | What will this explicitly **not** do? | an acceptance criterion saying so |

**Outcome is the spine — and it is the one most often missed.** It is easy to
write criteria that describe how a capability *behaves* — the steps it takes, the
order it takes them in, what it asks — and never state what must be **true when
it is done**. Those criteria read as thorough and verify nothing: a phase can
follow every step and still produce an artifact that is empty, incomplete, or
missing the thing it existed to produce.

Ask it plainly, and answer it in artifacts rather than actions: *what must exist
afterwards, and what must be true of it?* For anything that produces something —
a requirements catalogue, a plan, a set of mockups — this is the requirement.

**An outcome you cannot check is not finished.** Pair every outcome with the
question that settles it: *how would someone tell this is any good?* — phrased so
the answer is yes or no. This is the **fit criterion** (Volere): an objective
measure of what the requirement actually means, so its author, its implementer
and its tester read it the same way. "A requirements catalogue exists" passes
while the catalogue is empty; "every capability the person described appears in
it, and none appears that they did not" can be answered. Vague qualities are the
tell — *fast, intuitive, robust, user-friendly* are not outcomes until they carry
a number or an observable event.

**This does not displace the other dimensions.** Boundaries, edge cases and
failure behaviour are real guarantees and belong in the criteria alongside the
outcome ones. The rule is that outcome criteria must be **present**, not that
they must be the only ones. A requirement whose criteria describe only the
workflow is incomplete; a requirement that states its outcome *and* its edges is
finished.

### 8.1 The negative-space pass

The checklist above verifies that what you *recorded* is complete. It cannot
tell you the capability itself is under-specified — every dimension can be
answered about a requirement that still fails to promise something it obviously
should.

So before confirming, ask the inverse question once, deliberately:

> **What should this capability guarantee that it currently does not?**

Two moves that surface it reliably:

- **Read the description back as a promise and check each half is covered.** A
  description joining two capabilities with "and" needs criteria for *both*; it
  is common to find one half with none at all.
- **Ask what the capability must refuse, not just what it must do.** Coverage in
  one direction ("everything asked for gets built") rarely has its mirror
  ("nothing gets built that was not asked for"), and the missing direction is
  where unrequested work enters unnoticed.

Anything this turns up is a **new criterion**, not a note — and if the product
does not make that guarantee at all, say so plainly rather than writing a
criterion that reads as though it does.

**The stop-condition, stated once:** before the requirement is treated as
settled, every row above is answered — or, **only where the answer cannot be
obtained**, its cell is `Basis: assumed` with the guess recorded as a guess.

**`assumed` is for unobtainable answers, never for unasked questions.** This is
the load-bearing half of the rule, and the earlier wording — which allowed
`assumed` unconditionally — got it wrong. Marking a dimension `assumed` while
someone who could answer it is in the conversation is not honesty; it is
declining to ask, wearing honesty's label. It produces exactly the failure this
whole method exists to prevent: a requirement that looks properly recorded, is
formally compliant with the checklist, and quietly encodes a decision nobody
made. Before writing `assumed`, answer one question — *could I have found this
out, by asking the person or by reading the code?* If yes, `assumed` is not
available to you.

So the rule divides by whether the person who knows is reachable:

| Situation | Is `assumed` acceptable? |
|---|---|
| **A new project** (`/shipwright-project`) — the person is right there | **No.** Elicitation is not finished while a dimension is unanswered. Ask. Not asking is the defect; there is no budget excuse for it when the answer is one question away. |
| **An existing codebase** (`/shipwright-adopt`) — the decisions were made long ago, often by people who have left | **Yes**, for what the code cannot settle — deriving every requirement's full intent up front is work nobody would sit through. But each `assumed` requirement **must raise a work item to confirm it**, so it is a scheduled debt rather than a permanent guess. |
| **A change to a finished project** (`/shipwright-iterate`) | As for a new project where the operator is present; as for an existing codebase for pre-existing behaviour nobody can now explain. |

Never invent a confident answer. But never reach for `assumed` to avoid a
conversation either — between those two, the whole discipline sits.

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

- **Outcome** — "When this has run and succeeded, what exists that didn't before,
  and how would you check it is any good? What would make you say it ran but
  didn't actually work?"
- **Purpose** — "In one sentence, what can someone do after this exists that they
  couldn't before? Who is 'someone'? And what happens if we simply don't build
  it?" (the last one is the cheapest scope question there is — for a small team
  the binding problem is what to cut, not what to add)
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
  **The person is present, so `assumed` is not available (§8):** elicitation is
  not finished while a dimension is unanswered, and no requirement leaves this
  phase without acceptance criteria its author has confirmed. Producing a
  plausible-looking specification without asking is the failure mode this phase
  exists to prevent — the questions are the product.
- **`/shipwright-adopt` (brownfield)** — *infer-from-the-code first* (§3/§6): the
  vast majority of facts come from Layer-1 detection; the interview asks only the
  strategic questions the code cannot answer (profile, scope, nested projects)
  and then **confirms the requirements derived from the code** in business
  language rather than leaving them as guesses. **`assumed` is available here**
  (§8) for what the code cannot settle — nobody would sit through deriving every
  requirement's full intent up front — **but each `assumed` requirement raises a
  work item to confirm it**, so it is scheduled debt rather than a permanent
  guess. A derived requirement still gets acceptance criteria, written from the
  behaviour actually observed; "we could not ask anyone" is a reason to mark the
  basis honestly, never a reason to leave the criteria blank.
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
