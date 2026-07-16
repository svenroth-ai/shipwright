# Handoff: webUI traceability retrofit — run this as ONE iterate IN THE WEBUI REPO

> **This is NOT a monorepo sub-iterate. It does NOT run from the monorepo.** It runs in
> `C:\01_Development\shipwright-webui` (repo `svenroth-ai/shipwright-webui`), started from
> **webui's own triage / Inbox**, using the traceability tooling once it has shipped in the
> monorepo and synced to the plugin cache. TT8 (monorepo) only *authors* this brief; the
> work happens over there, as a separate git repo + PR flow.
>
> Monorepo handoff-reminder anchor: **`trg-17aaaccd`** ("Trace-Webui"). The real work anchor
> is created in the webui repo by the Kickoff below — do not reuse the monorepo id there.

## Preconditions (all must hold before you start)

1. The traceability campaign (`2026-07-15-test-traceability-layers`) has **merged** in the
   monorepo (TT1–TT8), so the shared engine + collector + Group-D detectors exist.
2. `bash scripts/update-marketplace.sh` **then** `uv run scripts/check_plugin_cache_sync.py
   --strict` have synced the updated plugins to `~/.claude/plugins/cache/shipwright/`. webui
   consumes the **cached** plugins (per `reference_webui_vendored_gates`-style vendoring), so
   an un-synced cache means webui runs the OLD tooling and this retrofit silently no-ops.
   **STOP CONDITION:** if `check_plugin_cache_sync.py --strict` reports drift, or the cached
   `backfill_test_links.py` / `test_links` collector is absent (i.e. the campaign has not
   merged + synced), **do not proceed** — re-sync first. Creating this monorepo PR does NOT
   by itself make the tool available in webui; the merge + `update-marketplace.sh` does.
3. You are on a clean webui working tree, on a fresh iterate branch (the backfill EDITS test
   files in place — keep the additive tag edits trivially reviewable/revertable).

## Intent

Bring webui up to the same traceability baseline the framework now enforces: tag webui's
existing tests with the FRs they cover, build the `test-traceability.json` manifest, and
prove the orphan/cross-layer detectors work on a real product repo — so the next time an
affordance is removed, the stale spec is caught automatically instead of by a lucky isolated
run (session `b2b8b521`).

## Kickoff (from the webui repo — establishes webui's OWN work anchor)

```bash
# in C:\01_Development\shipwright-webui
uv run shared/scripts/tools/triage_add.py \
  --kind improvement \
  --title "Traceability retrofit: tag existing tests -> FRs, build manifest, prove orphan detector" \
  --detail "Handoff from monorepo campaign 2026-07-15-test-traceability-layers (anchor trg-17aaaccd)"
```

Then run it as a single `/shipwright-iterate` (change_type=change; data/tags + docs).

## Runbook (the exact sequence, proven on the monorepo dogfood — TT8)

Run these from the webui repo root. This is the identical recipe TT8 ran on the monorepo;
substitute webui's paths. Adjust `--project-root` / test-root autodetect as needed.

```bash
# 1. DRY-RUN FIRST — see the counts before writing anything.
uv run shared/scripts/tools/backfill_test_links.py --project-root . --dry-run \
  --report-dir /tmp/webui-backfill-dry
#   Review: auto_written (high-confidence) vs proposals (low-confidence) vs
#   confirmed_orphan / possible_orphan / unmapped. NOTHING is written yet.

# 2. Split convention: webui's E2E flows likely DO use the NN- Playwright execution-order
#    prefix, which is NOT a Shipwright split id — leave --repo-follows-split-convention OFF
#    unless you confirm the NN- prefixes are genuine split ids (they usually are not).

# 3. APPLY high-confidence tags only (auto-write). Does NOT touch low-confidence tests.
uv run shared/scripts/tools/backfill_test_links.py --project-root .

# 4. Regenerate the manifest from the freshly-written tags. Resolve the cached compliance
#    plugin path concretely (do NOT hand-guess it):
COMPLIANCE_DIR=$(ls -d ~/.claude/plugins/cache/shipwright/shipwright-compliance/*/ | sort -V | tail -1)
uv run "${COMPLIANCE_DIR}scripts/tools/update_compliance.py" --project-root . --phase iterate
#   Verify the manifest bound the tags:
uv run python -c "import json;m=json.load(open('.shipwright/compliance/test-traceability.json'));\
print('tagged tests:', sum(len(l) for r in m['requirements'].values() for l in r['tests'].values()))"
#   NOTE: like the monorepo, webui's collector scans conventional root-level test dirs. If
#   webui's tests live under a non-conventional root, confirm the collector scans it (else the
#   written tags won't appear in the manifest — see the monorepo's TT8-coverage-delta.md
#   "Scope B" for that exact trap).

# 5. File the RESIDUE as ROLLED-UP triage (a count + a small sample — NOT one card per test):
#    - unmapped-summary  (tests that map to no live FR — REVIEW candidates, never accusations)
#    - proposals-summary (low-confidence candidate tags to confirm)
#    - repo-wide skip inventory (one summary card above ~10 findings)
#    Never auto-delete. Orphan retirement is a per-item HUMAN decision.

# 6. Run the Group-D detectors and confirm behavior (see Two-stage validation below).
```

## Two-stage validation (Spec §11 R5 — do not overclaim)

1. **Stage 1 — candidates:** the Stage-3 `backfill_test_links` run maps confidently-tagged
   tests, lists low-confidence proposals, and reports **orphan candidates** (tests that map
   to no live FR). The five known session specs have **no `@FR` tags today**, so backfill can
   only make them **review/orphan candidates** here — not hard failures.
2. **Stage 2 — strict detection:** for a confirmed candidate, add a reviewed `@FR` tag (or a
   historical/removed-FR record); **only then** does the strict `D-orphan` gate hard-validate
   it (a tag pointing at a removed/absent FR → MEDIUM finding). The detector cannot hard-flag
   an *untagged* stale test — **tagging is the precondition**. Do NOT promise automatic hard
   detection of untagged rot.

   - **What records the reviewed mapping:** the operator's `@FR` tag written into the webui
     test file (for a still-live FR) OR a webui triage disposition + a `## Removed
     Requirements` entry in webui's spec (for a retired FR). That committed tag/record — not
     a hunch — is what strict `D-orphan` reads when it regenerates base+head.
   - **Expected state per stage:** Stage 1 → the five named specs appear as
     candidates/residue (no automatic-detection claim). Stage 2 → regenerate webui's manifest
     and run strict `D-orphan`; the targets validate ONLY after the reviewed mapping exists.
   - **Missing-target handling:** if a proof target was renamed, moved, split, or retired
     (session `b2b8b521` already fixed four and retired the fifth), do NOT silently drop it —
     record an explicit triage disposition and substitute a currently-live orphan the Stage-1
     run surfaces as the validation case.

## The five known session specs (proof targets)

`campaigns-board-lane`, `36b`/`48`/`30-launch-copy`, `37b-bubble-lifecycle`,
`77-scrollback-replay` (ADR-065 / ADR-068-A1 / ADR-087). **Note:** session `b2b8b521`
already rewrote four of these to the current product and retired the fifth (spec 77), so
they may no longer be orphans. Use them as the **worked example that the detector logic is
sound**.

**Required accounting (do NOT silently drop any of the five):** the webui iterate's
acceptance MUST record an explicit disposition for **each** of the five named specs —
`still-orphan` (validated by strict `D-orphan` in Stage 2), `already-fixed` (with the current
path / ADR that fixed it), or `retired` (with the removal evidence). Additional currently-live
orphans the Stage-1 run surfaces MAY **supplement** the strict-`D-orphan` demonstration, but
must **not replace** the five-target accounting. A target that was renamed/moved is
re-pathed, not dropped.

## Acceptance (for the webui iterate)

- webui's confidently-mappable tests carry `@FR` tags; `test-traceability.json` renders a
  layer-aware RTM (per-FR Unit | Integration | E2E); orphan candidates are triage items
  (never silent deletions).
- The repo-wide skip inventory is filed as **rolled-up** triage (webui inherited `test.skip`
  rot — expect a summary card, not hundreds).
- A demonstration that `D-orphan` fires on a tagged-but-dead-FR case (the worked example or a
  current one) — the cross-repo proof that the detector bites (Stage 2).
- webui suite green; product source byte-stable (data/tags + docs only — ONLY test files may
  receive `@FR` tags).

## What the monorepo dogfood (TT8) actually found — a realistic yardstick

TT8 ran this exact recipe on the monorepo. Two scopes (see the monorepo's
`TT8-coverage-delta.md`): the **written/manifest-tracked** scope (`integration-tests/`: 162
tests → **3** high-confidence tags written) and the **complete repo-wide inventory** (7419
tests → **187** high-confidence candidates + **24** proposals, **7137** unmapped, **0** real
orphans, **50** skips). Two lessons for webui:

1. **Watch the collector scope.** If webui's tests live under a non-conventional root, tags
   written there won't land in the manifest (the monorepo hit this — 187 plugin-test
   candidates were inventoried-not-written for that reason). Confirm the collector scans
   webui's test root **before** writing at scale.
2. **Exclude test fixtures.** A naive full scan swept the monorepo's golden fixtures and
   produced 14 spurious "orphans" (synthetic FRs). Scope webui's run to real tests, not
   fixture mini-repos, or you will file false-positive orphan triage.

The low confident-map rate is EXPECTED — the monorepo tracks framework-internal FRs, so most
unit tests legitimately map to no product FR. webui is a product repo with UI/flow FRs, so
expect a **higher** confident-map rate at the E2E/flow layer, and the five known specs to
surface in Stage 1. Do not be alarmed by a large `unmapped` count; roll it up and move on.

## Notes

- webui is a separate repo/PR flow — follow webui's own PR + auto-merge conventions; open the
  webui PR from the webui branch, not from here.
- Keep it a data/tag change; orphan retirement is a per-item human decision.
- This brief is complete and self-contained; it does **not** execute from the monorepo and no
  monorepo PR can touch webui.
