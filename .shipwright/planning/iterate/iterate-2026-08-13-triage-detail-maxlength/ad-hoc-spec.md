# iterate-2026-08-13-triage-detail-maxlength (small complexity — no formal spec file)

shipwright-webui is lowering its promoted-task description cap from 20,000 to
~6,000 chars (`DESCRIPTION_MAX_LENGTH` in `server/src/external/_shared/helpers.ts`
+ `server/src/routes/triage.ts`) because a longer single-line launch command can
exceed the ~8,191-char Windows interactive console line limit and silently fail
to start Claude. The general `triage_item.schema.json` `detail` field has no
`maxLength`, and only the github_triage producer self-caps
(`_ARTIFACT_DETAIL_MAX_LEN = 1024`); every other producer can still mint an
unbounded `detail`.

## Acceptance criteria
- Add a shared `maxLength` (6000, matching webui's new cap) to
  `shared/schemas/triage_item.schema.json`'s `detail` field, both the `append`
  and `amend` event branches.
- Enforce it in `shared/scripts/triage.py::append_triage_item` (raise
  `ValueError` on an over-cap `detail`) so a pathologically long finding from
  any producer fails fast at write time instead of writing a record that
  fails to promote cleanly downstream.
- Close the same gap in `append_triage_item_idempotent` (a second writer
  building the same wire event) and the `amend` write path
  (`triage.amend_triage_item` / `lib.triage_amend.check_amend_detail` /
  `check_amend_fields`), since either left unguarded would bypass the
  append-side cap.
- `shared/scripts/triage.py` is pinned at an exact 882-line bloat-baseline
  ceiling (ADR-121, zero headroom); `shared/tests/test_triage_schema.py` is
  similarly pinned at exactly 558 lines. Both must stay at their exact
  current size — new tests for the append/idempotent/amend paths are homed
  in `shared/tests/test_triage_amend_schema.py` instead (which has headroom),
  matching that file's own documented precedent for exactly this situation.
