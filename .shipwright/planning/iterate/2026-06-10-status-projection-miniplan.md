# Mini-Plan: status-projection (campaign S2)

- **Run ID:** iterate-2026-06-10-status-projection

## Approach (chosen)

**New `shared/scripts/lib/campaign_status.py`** (pure logic, mirrors
`churn_merge.py`) — importable by both the plugin CLI and S3's shared
churn-resolver / finalize wiring:

1. `STATUS_LADDER = {"pending": 0, "in_progress": 1, "complete": 2}` — the
   monotonic ladder. `failed` / `escalated` are explicit/terminal (off-ladder).
2. `all_subs_complete(sub_iterates) -> bool` — **moved here from
   `campaign_progress.py`** as the canonical SSoT (lifecycle recompute rule).
3. `parse_campaign_skeleton(campaign_md_text) -> list[dict]` — parse the
   `## Sub-Iterates` markdown table → `[{id, slug, title}]` in row order
   (skip header + separator rows). Drives id/slug/title/**order**.
4. `_project_events(events_lines, slug) -> dict[id -> {commit, tests_passed,
   tests_total}]` — keep the **latest** (`ts`-max) `work_completed` event whose
   **top-level** `campaign == slug`; key by top-level `sub_iterate_id`. (S1
   shape — NOT `extras`.) Robust to blank/corrupt JSONL lines (skip).
5. `_merge_status(committed, projected) -> str` — never-downgrade: pick the
   higher-ladder status; `failed`/`escalated` preserved unless a projected
   `complete` supersedes (successful re-run).
6. `project_campaign_status(campaign_md_text, committed_status, events_lines,
   slug) -> (dict, summary)` — the **truly-pure core** (no filesystem): parse
   skeleton; project from `events_lines` (an iterable); build sub_iterates in
   skeleton order carrying commit/tests with field-level no-clobber; recompute
   lifecycle via `all_subs_complete`. Returns `(status_dict, summary)`.
7. `regenerate_campaign_status(campaign_dir, events_log) -> (dict, summary)` —
   thin **file-loading wrapper**: read `campaign.md` (raise if missing, AC3) +
   committed `status.json` (baseline if present) + `events_log` lines, then
   delegate to the pure core. No write / no git (the CLI writes).

## Design refinements (post external-review, both providers approved)

- **Pure-core / wrapper split** (OpenAI #1): logic core takes texts/objects so
  S3's churn-resolver can feed git-staged contents without a temp file.
- **`ts` robustness** (OpenAI #3 high, Gemini #3): keep the matching
  `work_completed` event with the max `(parsed_ts, file_index)` — datetime
  parse, file-order tie-break (last-wins); never lexical-sorts a raw string,
  never `KeyError`s on a missing `ts`.
- **Off-ladder guard** (Gemini #1): `_merge_status` special-cases
  `failed`/`escalated` (preserved unless a projected `complete` supersedes a
  re-run) and uses `LADDER.get(s, 0)` — no `KeyError`.
- **Strict skeleton** (OpenAI #6/#13, Gemini #2): require a `## Sub-Iterates`
  table with ≥1 row + unique non-empty ids; raise a targeted error otherwise.
  A producer↔parser contract test parses **real `campaign_init` output**.
- **Field-level no-clobber** (OpenAI #8, Gemini #4): projected `commit` /
  `tests_passed` / `tests_total` only overwrite committed values when present &
  meaningful (non-empty / non-null).
- **Drop non-skeleton committed subs** (OpenAI #7): skeleton is authoritative;
  dropped ids reported in the summary.
- **Explicit top-level lifecycle** (OpenAI #5): all-subs-complete →
  `complete` regardless of prior (overrides a stale `failed`); else prior
  preserved. Tested with prior `failed` + all complete.
- **Fixed CLI summary** (OpenAI #9/#12/#14): `{campaign, output_path,
  sub_count, matched_events, complete, dropped_subs, warnings}`; serialized
  idempotence test (regenerate∘regenerate == regenerate).

**Edit `plugins/shipwright-iterate/scripts/tools/campaign_progress.py`:**
- Add a walk-up `_shared_lib()` (mirror `campaign_init._find_shared_scripts`) and
  `from lib.campaign_status import all_subs_complete, regenerate_campaign_status`.
- Drop the local `_all_subs_complete` def; alias `_all_subs_complete =
  all_subs_complete` (no second definition — back-compat for any latent ref).
- Add `cmd_regenerate` + a `regenerate --campaign-dir` subparser (the thin CLI
  wrapper): calls the pure function, writes via the existing `_save_status`,
  prints a JSON summary.

**Tests:** new `plugins/shipwright-iterate/tests/test_campaign_status_projection.py`
(AC1–AC7, fixtures + the real S1-event boundary probe) and a `shared/tests`
unit for the pure lib (skeleton parse + ladder/never-downgrade + missing-md).

## Alternative considered (rejected)

**Keep the function in `campaign_progress.py` (plugin).** Rejected: S3's churn
resolver + finalize both live in `shared/`, so they would need a fragile
`shared → plugin` walk-up import (wrong dependency direction; no precedent —
`resolve_churn_conflicts` only ever does `from tools import finalize_iterate`
within shared). Placing the pure logic in `shared/scripts/lib` keeps the
dependency arrow plugin→shared and lets S3 `from lib.campaign_status import …`
directly. Confirmed with the user.

## Risks / mitigations

- **SSoT drift on `all_subs_complete`** — mitigated by a single canonical def in
  shared + an import alias in the plugin (no duplicate body).
- **`touches_io_boundary`** — round-trip Boundary Probe over the real S1 event +
  edge fixtures (corrupt line, missing md, empty events).
- **Cross-layout import** (dev monorepo vs plugin-cache) — reuse the proven
  `campaign_init` walk-up; assert importability in a test.
