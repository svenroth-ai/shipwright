# Mini-plan: test-infra-tag-class (rev 2)

Run: iterate-2026-11-18-test-infra-tag-class. Spec: `.shipwright/planning/iterate/2026-11-18-test-infra-tag-class.md`.

## Approach (chosen)
A source-declared third class in the F11 test-tag gate: a Python test marked `@pytest.mark.covers_none("tooling"|"infra")` whose file
is named exactly in a catalog read at the MERGE-BASE is counted as infrastructure. Judged in a dedicated pass over every test in a
changed file that carries `covers_none` (not only on the gate's own findings), so tagged tests, legacy tests and new tests are
treated by one rule. Never an F5c exemption, never a per-run label.

## Steps
1. `_tag_binding_py.py`: `py_infra_info(text, name)` -> per same-name declaration `(labels, bad_forms, has_covers)`. Granting is strict: literal `pytest.mark.covers_none(<one str literal in {tooling, infra}>)` only. Contradiction detection is loose: any `.covers` attribute on function, classes, class-body `pytestmark`, module `pytestmark` (Assign/AnnAssign/AugAssign), alias `mark.covers`. `_is_covers` stays exact; add `_is_covers_none` (shape `pytest.mark.covers_none` / `mark.covers_none`) and skip ONLY that in the digest decorators. `_covers()` untouched.
2. `shared/config/infra_test_paths.json` (exact paths) + loader in `tag_binding_gate.py`: `read(catalog,"base")`: `""` -> empty; `None` -> cannot enforce; malformed/invalid (not list of str, wildcard, `..`, backslash, absolute) -> empty + WARNING. Inside the existing try. WARNING when base and head catalog differ.
3. `_tag_binding_core.py`: `evaluate(..., infra_paths)`. New pass `_infra(...)` BEFORE the exemption loop: for each test id in a changed file whose head declarations carry any `covers_none`: normalise path, require base-catalog match, all siblings carry the same valid label and no covers, else `bad-infra-class` (message: "path not in the base catalog - add it in its own earlier merge" when relevant). Valid + would-be finding (`untagged-added`/`untagged-modified`) -> removed from findings, added to `v.infra`. Base-tagged same id or moved (digest match against base-tagged vanished tests) -> correction: base+head path in catalog, every FR/AC it carried keeps another head link, WARNING "X drops stand-in tag FR-..", else `bad-infra-class`. Infra ids leave `v.touched`. `_EXEMPTABLE` unchanged.
4. `tag_binding_gate._result`: summary adds `N infrastructure-classed`; `_HOW` mentions the marker only when a base catalog exists.
5. Register `covers_none` where `covers` is registered (root + plugin `pyproject.toml`; check `shared/templates` consumers).
6. `.github/CODEOWNERS`: explicit line for `shared/config/infra_test_paths.json`.
7. Docs: `.shipwright/agent_docs/conventions.md`, `docs/hooks-and-pipeline.md` (F11 row), `docs/guide.md` Ch. 8 + `gate_catalog` if the tag gate has an entry, `references/F11.md`/`F5c.md` note, `shared/glossary.md`; spec AC55 in FR-01.11.
8. Tests (`shared/tests/test_tag_binding_infra_class.py`; one root): happy path; bad label; non-literal/kw/extra arg; alias; outside base catalog; catalog widened in same diff; catalog `""`/`None`/malformed/wildcard entry; same-name siblings mixed; module `pytestmark` plain/`+=`/annotated/class-body; both markers; stand-in correction ok; correction leaving an AC without test refused; moved tagged test; plain tag-removed still fails; digest ignores exact marker but not `helpers.covers_none`; exemption + marker together; TS test with marker; infra count excluded from share; CI validator of the head catalog (entries exist, no wildcard). Siblings, move and catalog-read cases also as scratch-git gate runs.

## Rev 3 - external review integrated
- Digest filtering skips ONLY the exact `pytest.mark.covers_none` shape; the alias `mark.covers_none` is detected for validation, is never grantable, and still counts as a body edit (test: adding `mark.covers_none` changes the digest).
- Every validated infra test (new, legacy-untouched, accepted correction) is counted in `v.infra` and leaves `v.touched`; a superseded untagged finding is removed separately. Test the count and the share denominator for each case.
- `pytestmark` values that are not literal marks (a name, a variable, a call that is not `pytest.mark.*`) are unresolved: granting is refused (`bad-infra-class`, "unresolved pytestmark"). Tests for module and class references (`requirement_marks = [...]; pytestmark = requirement_marks`).
- Bootstrap: the catalog does not exist at this diff's merge-base, so none of the six seed files may be touched in THIS iterate (they are not; retagging is a follow-up merge). Stated here so the builder does not touch them.
- Verify empirically what `read(<absent path>, "base")` returns (`""` expected via `spec_text_at`); an absent-at-base catalog must be the silent empty case. Test it on a scratch repo.
- Extra tests: moved base-tagged test + marker + base path outside the catalog -> refused; a catalog file with module-level `covers_none` absorbs later new tests - disclosed, documented in `conventions.md`.
- Build-time checklist: enumerate every `covers` marker registration (root + 14 plugin `pyproject.toml`, `shared/templates`) from grep output; grep goldens/tests pinning the F11 summary line or exemption share (`exempted`), update deliberately.

## Alternatives considered
- Per-test F5c exemption code: self-reported word the gate cannot cross-check; same hole the operator wants closed.
- Real harness requirement (option D): puts a non-product capability in the requirement catalog and counts harness tests as coverage.
- Per-run label (`tooling`): relaxes every test of a mixed run.

## Risks / disclosed
- An exact-path entry for a real test merged in a reviewed PR (CODEOWNERS is the guard).
- Downstream reports still list infra tests as untagged (coverage cannot be inflated by them).
- Class judged only when a test is touched (ratchet).
