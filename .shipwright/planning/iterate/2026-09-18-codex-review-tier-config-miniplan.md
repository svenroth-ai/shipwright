# Mini-Plan: codex-review-tier-config

- **Run ID:** iterate-2026-09-18-codex-review-tier-config

## Chosen approach

Two independent, parallel model axes for `review`/`plan_review`, resolved by
which harness is actually driving:

- **Claude axis (existing, corrected):** `shared/scripts/lib/model_tier_config.py`
  `TIERS` gains `"fable"` as a fifth valid literal, alongside
  `opus`/`sonnet`/`haiku`/`inherit`. `RANKED_TIERS`/`RANK` stay untouched —
  `fable` is not added to either, staying floor-exempt (unorderable) exactly
  like `inherit` already is, because no capability ordering relative to
  opus/sonnet/haiku has been established for it and none should be guessed.
- **Codex axis (new, simplified after architecture review — see below):** a
  project-configurable Codex reviewer identity. `shipwright_model_config.json`
  gains two new *optional* top-level keys, `codex_review` and
  `codex_plan_review` (string, a Codex model slug). Unconfigured ⇒ the
  existing hardcoded default `gpt-5.6-sol` (byte-identical fallback, zero
  behavior change for every project that does not opt in). Whatever value is
  in play — configured, overridden, or the default — passes an unconditional
  syntactic allowlist and is then handed straight to `codex exec -m
  <value>`; **no live catalog call, no shipwright-maintained model list**.
  If the value does not name a real Codex model, Codex's own launch fails
  with its own error — there is nothing here for shipwright to keep in sync
  with Codex's evolving catalog.

## Simplification after architecture review (2026-09-18)

The original plan (this file's prior revision, post internal-plan-review)
added a `codex_model_catalog.py` module that shelled out to `codex debug
models` to validate a configured/overridden value before use, with a
memoized cache and a two-stage fail-open/fail-closed policy. Architecture
review returned **openai=reject, glm=revise/high**, both converging: the
live-catalog check buys "an invalid model is caught slightly earlier" at
the cost of a standing dependency on an undocumented CLI subcommand whose
shape had *already changed between two CLI versions checked in this same
session* (0.147.0 → 0.155.0 added `gpt-6-astra`) — the instability that
motivated building the check is also evidence the check itself is the less
stable of the two things. Its fail-closed-on-catalog-unreachable path also
made an *explicitly configured* run fragile to transient CLI/network flake
while an unconfigured run sailed through untouched — a perverse incentive
against using the feature.

**Accepted in full.** Dropped: `codex_model_catalog.py`,
`fetch_codex_model_catalog`, `validate_codex_reviewer_model`, the catalog
cache and its reset test seam, the catalog parser shape contract, and every
AC33 clause that depended on any of them. What remains — the config axis
itself, the syntactic allowlist, and letting `codex exec`'s own launch error
be the semantic check — is what glm separately confirmed as "the smallest
thing that would do." This also retires several earlier internal/external
review findings that existed only because the catalog layer did (the
`codex debug models` subprocess-hardening spec, its CI skip-guard shape,
its cache-lifetime docstring note) — moot, not re-litigated.

### Steps

1. `shared/scripts/lib/model_tier_config.py`: add `"fable"` to `TIERS`.
   Widen `load_model_config`'s `unknown_top` check (internal review finding
   #4 HIGH) to also accept two new optional top-level string keys,
   `codex_review` and `codex_plan_review` — same reader, same worktree→
   MAIN-root resolution, same non-dict fail-soft, same unhashable-value
   guard as every other key. Docstring note: `fable` is unranked, same
   treatment as `inherit`. Unit tests: `resolve_role_tier` accepts `fable`;
   `RANKED_TIERS`/`RANK` unchanged (extend existing frozen-set tests, don't
   replace); the two new keys round-trip through `load_model_config` with
   no spurious warning.
2. `shared/scripts/lib/review_record_model_tier.py`: give `fable` the same
   `inherit`-style "ran on an unrankable tier — floor not confirmed" wording
   at the `elif tier not in RANK` branch (internal review finding #6
   MEDIUM), plus a floor test for it.
3. `shared/schemas/model_config.schema.json`: add `"fable"` to the tier
   enum (Claude side only); add `codex_review`/`codex_plan_review` as new
   optional string properties (no enum — Codex's own launch is the
   validation, not the schema). Update the schema's description text, which
   currently says the file maps roles "to a Claude model tier" (internal
   review finding #11 LOW).
4. **Tier-literal drift fix (internal review finding #5 MEDIUM; marker
   approach revised after external plan review — both reviewers flagged
   free-text parsing as brittle):** update all six other hand-written
   enumerations of the Claude tier set in the same diff —
   `plugins/shipwright-iterate/skills/iterate/SKILL.md`,
   `plugins/shipwright-build/skills/build/SKILL.md`,
   `shared/scripts/tools/resolve_model_tier.py` (docstring/usage),
   `shared/scripts/lib/review_record_core.py`,
   `shared/scripts/lib/external_review_routing.py`, `docs/guide.md`. Each
   gets a stable, literal, machine-checkable marker string at the
   enumeration site — `opus/sonnet/haiku/inherit/fable` in that exact
   `sorted(TIERS)` join order — and the drift test asserts that exact
   literal string appears in each file, not a loose regex over surrounding
   prose. A future tier addition that forgets one of the six fails this
   test with a precise file:string diff instead of silently passing.
5. **Syntactic allowlist module** — new, small:
   `shared/scripts/lib/codex_model_catalog.py` is NOT built (dropped per
   the Simplification above); instead add
   `_CODEX_MODEL_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")`
   directly in `codex_review_transport.py` next to `CODEX_REVIEW_MODEL` —
   no separate module needed once there is no catalog logic to isolate.
   Unit test: the pattern rejects shell metacharacters
   (`&`, `|`, `^`, `"`, spaces) and accepts real slugs
   (`gpt-5.6-sol`, `gpt-6-astra`).
6. **Call-site inventory (external review MEDIUM, openai):** before
   changing `run_codex_review`'s signature, grep the full tree for every
   caller of `run_codex_review` and every invocation of
   `review_via_codex.py` (`shared/prompts/codex_review_dispatch.md`, any
   other dispatch path in `plugins/*/skills/*/references/*.md`). Update
   every Codex-driving call site found, and add one integration test that
   drives both the `review` and `plan_review` role mappings end-to-end
   through whichever dispatch path is confirmed live — not just
   `review_via_codex.py` in isolation — so a second, forgotten call site
   cannot bypass the new config precedence.
7. `shared/scripts/lib/codex_review_transport.py`: reinstate `model: str |
   None = None` as an explicit keyword argument on `run_codex_review`
   (internal review finding #2 HIGH — the exact seam the 2026-09-17 lock
   removed), never a module-global mutation. `model is None` → use
   `CODEX_REVIEW_MODEL`. `model` given → check
   `_CODEX_MODEL_SLUG_PATTERN` (reject → raise before launching anything);
   syntactically-valid values pass straight through to the `codex exec -m`
   argv, whatever they are — no further shipwright-side check. Return value
   gains the effective model actually launched (external review HIGH,
   AC35) — trivially "the given `model`, or `CODEX_REVIEW_MODEL` when
   `model was None`", since there is no fallback substitution to make this
   ambiguous. Module docstring gains a "supersedes AC2" note pointing at
   this run's ADR.
8. `shared/scripts/tools/review_via_codex.py`: resolve the role→config-key
   mapping explicitly ({spec,code,doubt} → `codex_review`, `plan_review` →
   `codex_plan_review`) by reading through the widened `load_model_config`
   (step 1 — one reader, not a second one, internal review finding #4
   HIGH). Add a new, distinctly-named `--codex-model` CLI flag for the
   per-run override (internal review finding #8 MEDIUM — never reuses
   `--review-model`/`--plan-review-model`, which stay Claude-tier-literal-
   only). Precedence: `--codex-model` > `shipwright_model_config.json` >
   hardcoded `gpt-5.6-sol`. Read the effective model back from
   `run_codex_review`'s return value for step 9's `--transport-note`. Unit
   tests: configured value used, override beats config, unconfigured uses
   the hardcoded default, syntactically-invalid value hard-errors at
   whichever layer it entered (config, override, or default — the default
   itself is trusted, never re-checked), the returned effective model
   matches what actually ran in every case above.
9. `record_review_pass.py` call sites in
   `shared/prompts/codex_review_dispatch.md`: require `--transport-note
   "<effective model>"` alongside `--transport codex` so the evidence names
   which model actually reviewed (internal review finding #9 MEDIUM, AC35).
10. Documentation (internal review finding #11 LOW): `AGENTS.md` (both the
    `gpt-5.6-sol` policy lines), `shared/prompts/codex_review_dispatch.md`
    (new flag), `docs/hooks-and-pipeline.md` config data-flow matrix,
    `docs/guide.md` Appendix B.
11. This run's ADR: record the AC2 supersession (internal review finding #2
    HIGH) — why a used, allowlisted, evidenced override is a stronger
    posture than an unused static lock — and the architecture-review
    simplification (catalog validator considered and dropped).
12. Full test suite; no UI, no E2E (this iterate has no startable web/cli
    surface change beyond the resolver layer — `Verification` surface is
    `cli`).

## Alternative considered — Option B: reuse `TIERS`/`RANKED_TIERS` for Codex too

Fold Codex's identities into the same `TIERS` enum as a set of new literals
(`"gpt-5.6-sol"`, `"gpt-5.6-terra"`, ...). **Rejected:** `TIERS` is a closed,
hand-maintained enum by design (mirrors the Agent tool's own closed schema,
which genuinely cannot accept arbitrary strings) — forcing Codex's
open-ended model space through that same closed gate would either freeze
Codex's list too (reintroducing the exact staleness bug that motivated this
iterate) or require widening `TIERS` validation to accept arbitrary
strings, silently loosening the Claude-side literal check that is
deliberately closed. Keeping the two axes structurally separate (closed
enum vs. allowlisted-then-Codex-validated string) is the change that maps
each axis's real integrity boundary correctly. Confirmed correct by the
architecture reviewer (glm) independent of the catalog-validator finding.

## Alternative considered — Option: live-query Codex's model catalog

The original chosen approach for this axis, before architecture review.
**Rejected** (see "Simplification after architecture review" above): adds a
standing dependency on an undocumented, already-observed-unstable CLI
subcommand to catch an error class Codex's own launch already catches,
with a fail-closed policy that penalizes the configured/overridden path
more than the unconfigured one.
