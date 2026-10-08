# Mini-plan: U1 test-tag gate + authoring instructions

Spec: campaign U1 (BRIEF section 2) + 4 carry-overs from U0's doubt review. Complexity: medium (cross-component: compliance collector, shared F11 verifier, iterate prompts). Spec impact: modify FR-01.11 (new AC41).

## Steps
1. Collector (`plugins/shipwright-compliance/.../collectors/_file_tags.py`, one call site in `test_links.py`, which shrinks by one line): fold a wrapped multi-line `test(`/`it(`/`describe(` head onto one line before parsing and enumerating; bind pytest class-level `@pytest.mark.covers` and module-level `pytestmark`; dedupe a propagated hit that repeats a per-test hit. Reuses the frozen grammar's own marker test and FR/AC canonicaliser.
2. Gate `verifiers/tag_binding_gate.py` (`check_test_tag_binding`, registered in `CLAIM_CHECKS`): regenerates base+head through `_layer_coverage_regen.regenerate_base_head(with_evidence=False)`; an evidence-free head is now memoised next to the base, so the removal gate and this gate share one regeneration per run. Both manifests validated with `_keystone_base_manifest.require_manifest_shape` (ReadError -> STOP).
3. Verdict `_tag_binding_core.py` (pure): untagged-added (head untagged - base untagged, minus moves matched by normalised body digest against base tests that vanished in changed files), tag-removed, untagged-modified (legacy untagged test in a changed file whose normalised digest changed), new invalid tag, new unresolved (orphan) tag, per-diff/blanket exemption. Per-test exemptions from the F5c `exemptions` block: `fixture-or-helper` only when pytest would not collect the function, `mechanical-refactor` only when identifier-anonymised digests are equal. A new tag outside the run's `affected_frs`/`new_frs` WARNs.
4. Identity `_tag_binding_identity.py`: Python digest = AST dump of args + body minus docstring (name and decorators excluded: rename -> move, parametrize case/mark -> no edit); TS digest = comment/whitespace-stripped token stream after the title, trailing commas dropped; anonymised variant for mechanical-refactor; `would_collect` follows pytest's rules statically.
5. Failure modes: non-git -> SKIP; no commit / no merge-base / collector or archive failure / diff not listable / malformed manifest / crash -> STOP with remediation, at every complexity.
6. Carry-overs: missing `exemptions` key prints `not recorded (legacy entry)`; `run_claim_checks` catches SystemExit (KeyboardInterrupt propagates); no-import-of-iterate_checks rule in the registry docstring + docs table preamble + a meta-test; crashed check reported under its module's `CHECK_NAME`.
7. Authoring: SKILL.md Step 6, path-a ("Tag each test"), path-b Step 6, path-c regression test tag, F0.md ratchet = safety net, F5c `exemptions` always written + test_exemption semantics, F12 share line.
8. Tests (all tagged `FR-01.11/AC41`): core rules on dicts, real-git integration incl. WebUI-shaped Playwright project and the full F11 list, collector shape tests, registry carry-overs.

## Alternatives considered
Parse tags with `lib/fr_tag_grammar.py` directly; read the committed base manifest only; a repo-wide untagged baseline file; per-diff exemption flag.
