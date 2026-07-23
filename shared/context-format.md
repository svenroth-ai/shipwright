# The CONTEXT.md format — a project's domain glossary

**Companion to `shared/requirement-elicitation.md` §7.** When the grilling method
sharpens a term (§4 there), it is written into the target project's `CONTEXT.md`
in the format below.

`CONTEXT.md` lives **in the target project** (the app being built), not in this
framework. It is the shared vocabulary of that project's domain — the single
place that settles what each word means, so two people and the assistant read a
requirement the same way.

---

## 1. What CONTEXT.md is — and what it is not

**It is** a glossary of the target project's **domain** language: the nouns and
verbs the product is described in (Order, Cancellation, Customer, Seam), each with
one settled meaning.

**It is not** a specification, a design doc, or an implementation scratch pad.
*"CONTEXT.md should be totally devoid of implementation details."* No file paths,
no function names, no schemas — those live in `architecture.md` and the code. If
an entry starts describing *how* something is built, it is in the wrong file.

**It is not `shared/glossary.md`.** This is the collision to keep straight:

| File | Whose vocabulary | Example terms |
|---|---|---|
| `shared/glossary.md` (this framework) | **Shipwright's own** machinery, read by hooks, audits, agents | Allowlist, Ratchet, Producer, Canon-Gate |
| `CONTEXT.md` (each target project) | the **target project's business domain** | Order, Cancellation, Customer, Seam |

They never merge. A term about how Shipwright works goes in `shared/glossary.md`;
a term about what the *product* means goes in the product's `CONTEXT.md`.

## 2. The format

Three sections, following Matt Pocock's own `CONTEXT.md`:

```markdown
# CONTEXT.md — <project> domain glossary

<one-line statement of what this project is>

## Language

**Order** — a customer's confirmed purchase of one or more items.
_Avoid_ "cart" for a confirmed order — a cart is unconfirmed.

**Cancellation** — voiding an Order before it ships. Partial cancellation
(some line items) is distinct from full cancellation.

## Relationships

- A Customer has many Orders; an Order belongs to exactly one Customer.
- An Order has many line items; a Cancellation targets one or more line items.

## Flagged ambiguities

- "account" was used for both Customer and User — resolved 2026-07-23 to mean
  the paying **Customer**; the logged-in identity is a **User**.
```

- **Language** — each term in **bold**, its definition in plain prose, and an
  optional `_Avoid_` line rejecting a confusable synonym so the wrong word stops
  spreading.
- **Relationships** — the cardinality between terms (one-to-many, one-to-one),
  one bullet each. This is where "an Order belongs to one Customer" is settled.
- **Flagged ambiguities** — the resolution log: each terminology clash that was
  caught (elicitation §4) and how it was decided, so the decision does not get
  re-litigated.

## 3. Rules

- **One term, one meaning.** If a word carries two meanings, that is a flagged
  ambiguity to resolve, not two entries.
- **No implementation detail.** Pure glossary (§1).
- **Small on purpose.** Only terms that are actually ambiguous or load-bearing.
  A glossary that restates the dictionary is noise.
- **Rationale goes to an ADR, not here.** *Why* a decision was taken belongs in a
  linked ADR (elicitation §7); `CONTEXT.md` records only *what a term means*.

## 4. Where it lives

- **Single-domain project:** one `/CONTEXT.md` at the project root, plus
  `/docs/adr/` for the decision records it references.
- **Multi-domain project:** a top-level `CONTEXT-MAP.md` pointing to a
  per-domain `CONTEXT.md` inside each domain's directory, so each bounded context
  keeps its own vocabulary without collisions.

---

> **Attribution.** The `CONTEXT.md` format — the Language / Relationships /
> Flagged-ambiguities structure, the `_Avoid_` convention, and the
> "pure glossary, no implementation" rule — is adopted from Matt Pocock's
> `domain-modeling` skill and his repository's own `CONTEXT.md`
> (https://github.com/mattpocock/skills, MIT, © Matt Pocock).
