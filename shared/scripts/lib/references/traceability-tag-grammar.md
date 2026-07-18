# `@FR` Tag Grammar — reference (traceability Spec §4 / R4)

> Frozen P1 contract. The executable reference is `shared/scripts/lib/fr_tag_grammar.py`;
> this document is the human-readable spec of the same grammar. Production collectors
> (campaign TT1's `test_links`) MUST bind identically.

## The one concept

The canonical machine token is **`@FR-XX.YY`** — `FR-`, two digits, a dot, two digits.
One or more per test. Where it lives is idiomatic per runner; a single grammar understands
all forms. Canonical regex: `@FR-\d{2}\.\d{2}`.

A requirement id like `FR-7` is a legal *spec heading* id but is **never** a canonical
manifest/tag id — tags are always two-digit.two-digit.

## Accepted forms

| # | Runner | Form | `tag_source` | Binds to |
|---|--------|------|--------------|----------|
| 1 | pytest (Python) | `@pytest.mark.covers("FR-01.03", "FR-01.04")` | `pytest_marker` | the decorated function (read from the **AST**) |
| 2 | TS/JS comment | `// @covers FR-01.03` on the line **immediately preceding** a test | `covers_comment` | the `it(`/`test(` on the very next line |
| 3 | Playwright | `test('…', { tag: ['@FR-01.03'] }, …)` | `native_tag` | the test on that declaration line |
| 4 | Vitest | `it('does X @FR-01.03', …)` (token at the **end** of the title) | `title_suffix` | the test whose title ends with it |

Notes:
- **pytest** is parsed structurally from the AST — robust binding, never a naive grep.
- The TS/JS side of this *reference* is a **limited, documented** line matcher (Python cannot
  AST-parse TypeScript). The production JS-side matcher (TT1) generalises it; the grammar
  (canonical token, malformed handling, `tag_source` vocabulary) is identical.
  - **Documented reference limitations** (the TT1 matcher lifts these, the grammar stays the same):
    the reference binds only the **single-line** forms — a `test(` / title / `tag:` array must be
    on one line; a multi-line `test(\n  '…',\n  { tag: [...] })` is not bound. It does not exclude
    `test('…')` occurring inside a string/comment (the fixtures never do this). It ignores
    `test.describe(` (a suite). Use single-line forms in fixtures; TT1's tokenizer handles the rest.
- **Binding is strict:** a `// @covers` comment binds only to a test declaration on the
  **immediately following** line (a blank/intervening line breaks it); a title tag binds only
  when it is a **suffix** of the title (prefix/middle occurrences are ambiguous → informational,
  never bound). Binding targets are `it(`/`test(` only — `describe`/suite-level tag propagation
  is a production-collector feature (TT1), out of scope for the reference.
- Multiple ids may appear (`@pytest.mark.covers("FR-01.03", "FR-01.04")`;
  `// @covers FR-01.03, FR-01.04`).

## Malformed → `invalid_tags`

A token that looks like an FR tag but is not canonical is recorded in `invalid_tags`
(`{test, raw}` — an optional `reason` may be carried), **never** counted as coverage. The
matcher captures the **whole** token run, so trailing junk cannot masquerade as a valid prefix:

| Raw | Why |
|-----|-----|
| `@FR-1.3` | single-digit segments (not two-digit.two-digit) |
| `@FR01.03` | missing the `-` delimiter |
| `@FR-01.3` | second segment is one digit |
| `@FR-01.03x` / `@FR-01.03.4` | trailing continuation — not the exact canonical token |
| `covers(42)` | non-string marker argument |

Malformed tags on a **changed** test are a hygiene failure in the production gate (TT4);
P1 only records them.

## Binding & enforcement rules (carried by the production gates, not P1)

- A **grep-only** hit that cannot be unambiguously bound to a test is *informational*,
  never satisfies a hard gate (R4).
- "Covered at a layer" requires a tagged test that is **enabled AND executed-passing** in
  that layer's evidence (R1) — a statically-present tag on a skipped test closes nothing.
- Enforcing gates **regenerate** the base+head index themselves and compare; the committed
  `test-traceability.json` is derived/RTM-visibility only (R3).

## `tag_source` vocabulary (closed)

`pytest_marker` · `covers_comment` · `native_tag` · `title_suffix`
(SSoT: `fr_tag_grammar.TAG_SOURCES`, mirrored by the manifest `tag_source` enum).

## Folded FR ids — `## FR-Fold-Map`

A spec clean-up may **fold** a fine-grained FR into the broader capability FR that now
owns it. Folded ids are never retired; the spec records them in an alias table so old
references keep resolving — **including your test tags, which you do not have to rewrite:**

```markdown
## FR-Fold-Map

| Folded ID | → Survivor | Reason | Was (original name) |
|-----------|-----------|--------|---------------------|
| `FR-01.44` | `FR-01.28` | delta | Embedded terminal appearance |
```

A tag on `FR-01.44` then counts as coverage of `FR-01.28`, and the link records
`resolved_from: "FR-01.44"` so an auditor can see why. Rules worth knowing:

- **Fallback, never override.** A tag naming a *live* FR always binds to that FR; the
  fold-map is consulted only for a tag that would otherwise orphan. An id that is both
  active and listed as folded keeps its own coverage obligation (its fold entry is inert).
- **Terminal decides.** A chain `A → B → C` resolves to `C` if `C` is active, passing
  through `B` whether or not `B` is still live.
- **Broken edges fail closed.** A cycle, a survivor that is removed or absent, the same id
  folded to two different survivors, or a malformed row → the tag keeps its orphan status
  and a typed entry lands in the manifest's `fold_defects` (surfaced by D-orphan as LOW
  hygiene). The fold-map can rescue a tag; it can never invent coverage.
- **Ids are case-sensitive** here exactly as in a tag: `fr-01.44` is an `unparsable_row`
  defect, not a silent match.
- Fold-map rows are **never** read as live requirements — backticked or not.

SSoT: `fr_fold_map` (`FOLD_DEFECT_KINDS`, `resolve_fold`), shared by the TT1 collector
and the backfill engine so the two cannot disagree.
