# Mini-Plan: canon-lookbehind-hyphen

- **Run ID:** iterate-2026-08-01-canon-lookbehind-hyphen
- **Spec:** `iterate-2026-08-01-canon-lookbehind-hyphen.md`

## Approach (chosen)

Add `-` to the negative-lookbehind character class of the **two separator
patterns** of each migration, leaving the two quoted-literal patterns alone.

```
r"(?<![\w/.\\])compliance/"   →   r"(?<![\w/.\\-])compliance/"
r"(?<![\w/.\\])compliance\\"  →   r"(?<![\w/.\\-])compliance\\"
```

Eight literals across four migrations. Then: retire the allowlist entries the
fix provably empties, repurpose the inverted regression test, and record the
decision reversal.

**Why this and not the alternative.** The other option the report names is
*anchor on a path separator* — rewrite the head as an explicit
`(?:^|[^\w/.\\-])` or a `(?<=[\s"'(=:])` positive lookbehind. Rejected: it
changes the pattern's *shape*, not just its alphabet, so every one of the ~1,855
current matches would have to be re-derived rather than reasoned about as a
subset. The character-class edit has a property the rewrite does not — the new
match set is provably a **strict subset** of the old one, which is what makes
"zero true positives lost" a one-line argument instead of a full re-audit. A
positive lookbehind would also newly require *some* preceding character, silently
dropping matches at the start of a line, which is exactly where a bare
`compliance/foo` reference in a JSON value or a bullet lives.

## Steps

| # | File | Action |
|---|---|---|
| 1 | `shared/tests/test_path_canon_windows.py` | **Red first.** Add the three pinning tests: hyphen-suffixed dirname does not match (POSIX + Windows, all migrations); canonical `.shipwright/<dirname>/` stays unmatched; only the separator patterns carry the hyphen. Confirm they fail. |
| 2 | `shared/scripts/lib/artifact_migrations.py` | Add `-` to the 8 separator-pattern lookbehinds; rewrite the block comment above them to state what the class means and why the quoted patterns differ. |
| 3 | `shared/tests/test_artifact_path_canon_manifest_allowlist.py` | Invert `test_manifest_content_really_trips_a_migration` → `test_manifest_content_trips_no_migration`; add `test_retained_manifest_exemption_still_has_a_basis`; rewrite the module docstring, which currently explains the bug as live. |
| 4 | `shared/scripts/lib/artifact_migrations.py` | Remove the three exemptions the fix empties; correct the rationale on the entries kept for churn reasons so no comment asserts a false positive that no longer exists. |
| 5 | — | Re-run probe 4 against the *edited* manifest to confirm the removals leave the lint green. |
| 6 | — | Full `shared/tests` root; then the other roots F0 covers. |

## Risks

- **Line budget.** `artifact_migrations.py` sits at 632 lines against a limit of
  300 under the ADR-091 bloat exception, so the anti-ratchet blocks any growth
  past 632. Step 2 and step 4 must net-shrink; comment corrections are
  in-place rewrites, never additions. Check with the pre-commit hook against the
  **staged** content before committing.
- **Removing an exemption re-arms a landmine.** Only entries measured to zero
  findings go, and only hand-written ones — the generated churn artifacts
  (`test-traceability.json`, `shipwright_bloat_baseline.json`) keep their
  exemptions on independent grounds, because their content is regenerated every
  iterate and a future regeneration failing the lint would go red on an
  *unrelated* run. That is the failure mode iterate-2026-07-16 already paid for.
- **The inverted test could go vacuous.** `test_manifest_content_trips_no_migration`
  passes trivially if the sample string stops containing a hyphenated dirname at
  all. Pin it with a sibling assertion that the *bare* form of the same dirname
  still trips, so the sample is proven to still be capable of tripping.
